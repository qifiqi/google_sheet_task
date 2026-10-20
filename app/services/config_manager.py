# stdlib json 仅保留 parse_constant 解析钩子用途（orjson 不支持解析钩子）；
# 其余序列化统一走 app.utils.json_utils。
import json
import threading
import time
from typing import Any, Dict, Iterable

from app.exceptions import BadRequestError
from app.repositories import system_config_repository
from app.utils.json_utils import dumps
from app.utils.logger import get_logger
from app.utils.value_parser import coerce_bool as _coerce_bool_value

logger = get_logger(__name__)

# 负缓存哨兵：标记"数据库中确认不存在"的 key，避免每次 get 都重复查库。
# 哨兵只存在于进程内缓存，永远不会写入数据库或对外返回。
_MISSING = object()

# 远端配置全量加载失败后的退避窗口：避免故障期间每次 get 都触发全量拉取。
_LOAD_RETRY_SECONDS = 5.0

# 值里包含这些关键字的配置项，日志中打码，防止敏感信息进入日志文件。
_SENSITIVE_KEY_HINTS = ('token', 'secret', 'password', 'credential', 'apikey')

# 受保护配置键：身份与网络链路的关键安全配置，禁止经 HTTP 配置接口写入
# （/api/config POST 与 /system-configs PUT 一并拦截）。这些键只能由运维
# 经环境变量或服务端脚本（set_config）设置，防止篡改 JWT 签名密钥、
# 或把平台 Google Sheet 流量导向外部代理（凭据窃取面）。
PROTECTED_CONFIG_KEYS = ('JWT_SECRET_KEY', 'SECRET_KEY', 'proxy_url')


def assert_keys_writable(keys: Iterable[Any]) -> None:
    """校验待写配置键不含受保护键，命中抛 BadRequestError（调用方不 catch，走全局信封）。"""
    blocked = sorted({str(k) for k in keys if str(k) in PROTECTED_CONFIG_KEYS})
    if blocked:
        raise BadRequestError(
            f"配置项 {', '.join(blocked)} 为受保护配置，禁止经接口写入；"
            "请由运维通过环境变量或服务端脚本设置"
        )


def _mask_config_value(key: str, value: Any) -> Any:
    lowered = str(key).lower()
    if any(hint in lowered for hint in _SENSITIVE_KEY_HINTS):
        return '***'
    return value


def mask_config_value(key: str, value: Any) -> Any:
    """公开脱敏出口：key 含 token/secret/password/credential/apikey 时值打码。

    所有把配置值下发到响应（管理端诊断/列表端点）的路径必须经过本函数。
    """
    return _mask_config_value(key, value)


def _is_masked_echo(key: str, value: Any) -> bool:
    """识别管理端"脱敏回显被原样提交回写"：敏感键 + 掩码字面量 `***`。

    管理端列表/编辑弹窗以脱敏值预填表单，用户只改描述等元数据时会把掩码
    字面量原样回传；若照单写库，真实值会被 `***` 静默覆盖。此类提交一律
    视为"未修改 value"处理。
    """
    return (
        any(hint in str(key).lower() for hint in _SENSITIVE_KEY_HINTS)
        and isinstance(value, str)
        and value == '***'
    )


def _serialize_config_value(value: Any) -> str:
    """配置值入库序列化。

    字符串原样入库（与历史数据保持一致）；bool/None/数字/容器统一走 JSON，
    保证读回时能恢复原始类型。JSON 无法表达的类型退回 str() 兼容。
    """
    if isinstance(value, str):
        return value
    try:
        return dumps(value)
    except (TypeError, ValueError):
        return str(value)


def _reject_json_constant(name: str):
    """json.loads 的 parse_constant 钩子：拒绝 NaN/Infinity 等非法常量。"""
    raise ValueError(f"非法 JSON 常量: {name}")


def _deserialize_config_value(value: Any) -> Any:
    """配置值读回反序列化，与 _serialize_config_value 对称（收窄版）。

    - 布尔/None：精确匹配 json.dumps 产物（true/false/null）与历史 str() 产物
      （True/False/None），不再对任意 t/f/n 开头的词做解析尝试；
    - 容器/JSON 字符串：以 { [ " 开头才尝试解析；
    - 数字：仅当整串是合法 JSON 数字才还原为 int/float（json.dumps(数字) 的产物），
      解析结果为 NaN/Infinity 直接按原字符串返回；
    - 其余一律原样返回字符串。历史纯数字字符串 key 若被静默转成数字，由调用方
      （set_config 的写入方）负责用 json.dumps 显式表达字符串意图。
    """
    if not isinstance(value, str):
        return value

    # 旧数据兼容层：str(True)/str(False)/str(None) 的历史产物
    if value == 'True':
        return True
    if value == 'False':
        return False
    if value == 'None':
        return None
    # json.dumps 的布尔/None 产物（精确匹配）
    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'null':
        return None

    stripped = value.strip()
    # 容器与 JSON 字符串：仅对可能构成 JSON 的开头字符做解析尝试
    if stripped[:1] in ('{', '[', '"'):
        try:
            return json.loads(stripped, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value

    # 数字：整串必须是合法 JSON 数字（json.dumps(数字) 的入库形态）才还原
    if stripped[:1].isdigit() or stripped[:1] in ('-', '.'):
        try:
            parsed = json.loads(stripped, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
        if isinstance(parsed, (int, float)):
            return parsed
    return value


def coerce_bool(value: Any, default: bool = False) -> bool:
    """统一的布尔配置解析入口（实现见 app/utils/value_parser.coerce_bool）。

    本包装仅附加配置存储的 ``_MISSING`` 哨兵语义：缺失键返回 default。
    """
    if value is _MISSING:
        return default
    return _coerce_bool_value(value, default)


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        # _loaded 区分"库里确实没有配置"和"还没加载过"，避免空库时每次 get 都全表查询
        self._loaded = False
        self._load_failed_at = 0.0
        self._lock = threading.RLock()
        self._app = None

    def init_app(self, app):
        self._app = app

    def _get_app_context(self):
        try:
            from flask import has_app_context, current_app
            if has_app_context():
                return current_app.app_context()
        except Exception:
            pass

        if self._app is not None:
            return self._app.app_context()

        return None

    def _load_configs(self):
        """加载所有配置到缓存。调用方必须已持有 self._lock。"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error("加载配置失败: Working outside of application context.")
                return

            with ctx:
                rows = system_config_repository.list_rows()
                cache: Dict[str, Any] = {}
                for row in rows:
                    cache[row["key"]] = _deserialize_config_value(row["value"])
                self._cache = cache
                self._loaded = True
                self._load_failed_at = 0.0
                logger.debug(f"加载了 {len(rows)} 个配置项")
        except Exception as e:
            self._load_failed_at = time.monotonic()
            logger.error(f"加载配置失败: {str(e)}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            if not self._loaded:
                if (
                    self._load_failed_at
                    and time.monotonic() - self._load_failed_at < _LOAD_RETRY_SECONDS
                ):
                    return default
                self._load_configs()

            if key in self._cache:
                value = self._cache[key]
                return default if value is _MISSING else value

            # 缓存已加载但没有该 key：单查数据库确认（首次），之后走负缓存
            try:
                ctx = self._get_app_context()
                if ctx is None:
                    logger.error(f"从数据库加载配置失败: {key}, 错误: Working outside of application context.")
                    return default

                with ctx:
                    row = system_config_repository.get_row(key)
                    if row:
                        value = _deserialize_config_value(row["value"])
                        self._cache[key] = value
                        return value

                    # 数据库确认不存在：记录负缓存，后续调用直接返回 default
                    self._cache[key] = _MISSING
                    return default
            except Exception as e:
                logger.error(f"从数据库加载配置失败: {key}, 错误: {str(e)}")
                return default

    def get_all_configs(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取所有配置；force_refresh=True 时强制从数据库重新加载"""
        with self._lock:
            if force_refresh or not self._loaded:
                in_backoff = (
                    not force_refresh
                    and self._load_failed_at
                    and time.monotonic() - self._load_failed_at < _LOAD_RETRY_SECONDS
                )
                if not in_backoff:
                    self._load_configs()
            return {k: v for k, v in self._cache.items() if v is not _MISSING}

    def get_cache_snapshot(self) -> Dict[str, Any]:
        """诊断用：返回缓存原始快照，负缓存哨兵显示为 None。"""
        with self._lock:
            return {k: (None if v is _MISSING else v) for k, v in self._cache.items()}

    def get_db_config_rows(self) -> list:
        """配置行原始列表（管理端列表/诊断端点消费，含 description）。"""
        return system_config_repository.list_rows()

    def update_config_row(self, key: str, fields: Dict[str, Any]):
        """单条配置行更新 + 缓存刷新（/system-configs PUT 语义）；不存在返回 None。

        行级写入走 repository，缓存/负缓存刷新留在本层（数据层分层规则）。
        受保护键拒绝更新 value（description 等元数据修订不受限）；
        敏感键的掩码回显（`***`）视为未修改，跳过 value 写入。
        """
        if 'value' in fields:
            assert_keys_writable([key])
            if _is_masked_echo(key, fields['value']):
                fields = {k: v for k, v in fields.items() if k != 'value'}
                logger.info(f"配置 {key} 提交值为脱敏回显，跳过 value 更新")
        if not fields:
            return system_config_repository.get_row(key)
        updated = system_config_repository.update(key, fields)
        if updated is None:
            return None
        try:
            self.refresh_cache()
        except Exception as e:
            logger.warning(f"更新配置后刷新缓存失败: {e}")
        return updated

    def set_config(self, key: str, value: Any, description: str = None) -> bool:
        """设置配置值"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error(f"设置配置失败: {key}, 错误: Working outside of application context.")
                return False

            with ctx:
                value_str = _serialize_config_value(value)
                system_config_repository.upsert(key, value_str, description=description)

                # 缓存存"读回形态"（反序列化后），与 _load_configs/refresh 一致，
                # 保证同一 key 在 set 与缓存刷新两个生命周期内 get 返回类型恒定。
                with self._lock:
                    self._cache[key] = _deserialize_config_value(value_str)

                logger.info(f"设置配置: {key}")
                logger.debug(f"设置配置: {key} = {_mask_config_value(key, value)}")
                return True

        except Exception as e:
            logger.error(f"设置配置失败: {key}, 错误: {str(e)}")
            return False

    def delete_config(self, key: str) -> bool:
        """删除配置"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error(f"删除配置失败: {key}, 错误: Working outside of application context.")
                return False

            with ctx:
                deleted = system_config_repository.delete(key)
                if not deleted:
                    return False

                # 从缓存中删除
                with self._lock:
                    self._cache.pop(key, None)

                logger.info(f"删除配置: {key}")
                return True

        except Exception as e:
            logger.error(f"删除配置失败: {key}, 错误: {str(e)}")
            return False

    def update_configs(self, configs: Dict[str, Any]) -> bool:
        """批量更新配置（/api/config POST 语义；受保护键直接拒绝）

        敏感键的掩码回显（`***`）视为未修改，跳过该键的 value 写入。
        """
        assert_keys_writable(configs.keys())
        try:
            skipped_echo = [key for key, value in configs.items() if _is_masked_echo(key, value)]
            if skipped_echo:
                logger.info(f"以下配置提交值为脱敏回显，跳过更新: {', '.join(skipped_echo)}")
            pending = {k: v for k, v in configs.items() if k not in skipped_echo}
            if not pending:
                logger.info("批量更新请求全部为脱敏回显，无实际变更")
                return True
            for key, value in pending.items():
                success = self.set_config(key, value)
                if not success:
                    logger.error(f"更新配置失败: {key}")
                    return False

            # 强制重新加载缓存，确保其他进程/线程能获取到最新配置
            with self._lock:
                self._load_configs()

            logger.info(f"批量更新了 {len(configs)} 个配置项")
            return True
        except Exception as e:
            logger.error(f"批量更新配置失败: {str(e)}")
            return False

    def get_google_sheet_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取Google Sheet相关配置；force_refresh=True 时强制从数据库重新加载"""
        with self._lock:
            if force_refresh or not self._loaded:
                self._load_configs()

            # 基于当前缓存构造配置字典（数据库里有什么就返回什么）
            configs = {k: v for k, v in self._cache.items() if v is not _MISSING}

        # 兼容性处理：老版本可能把这些字段存成 dict，需要统一转换为 list
        param_positions = configs.get('parameter_positions', [])
        check_positions = configs.get('check_positions', [])
        result_positions = configs.get('result_positions', [])

        if isinstance(param_positions, dict):
            param_positions = list(param_positions.values())
        if isinstance(check_positions, dict):
            check_positions = list(check_positions.values())
        if isinstance(result_positions, dict):
            result_positions = list(result_positions.values())

        configs['parameter_positions'] = param_positions
        configs['check_positions'] = check_positions
        configs['result_positions'] = result_positions

        return configs

    def refresh_cache(self):
        """强制刷新配置缓存"""
        try:
            with self._lock:
                self._load_configs()
            logger.info("配置缓存已刷新")
        except Exception as e:
            logger.error(f"刷新配置缓存失败: {str(e)}")

# 全局配置管理器实例
config_manager = None
_config_manager_lock = threading.Lock()

def get_config_manager():
    """获取配置管理器实例"""
    global config_manager
    if config_manager is None:
        with _config_manager_lock:
            if config_manager is None:
                config_manager = ConfigManager()
    return config_manager
