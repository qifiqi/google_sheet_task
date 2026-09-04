import json
import threading
from typing import Any, Dict, Optional
from app.repositories import system_config_repository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 负缓存哨兵：标记"数据库中确认不存在"的 key，避免每次 get 都重复查库。
# 哨兵只存在于进程内缓存，永远不会写入数据库或对外返回。
_MISSING = object()

# 值里包含这些关键字的配置项，日志中打码，防止敏感信息进入日志文件。
_SENSITIVE_KEY_HINTS = ('token', 'secret', 'password', 'credential', 'apikey')


def _mask_config_value(key: str, value: Any) -> Any:
    lowered = str(key).lower()
    if any(hint in lowered for hint in _SENSITIVE_KEY_HINTS):
        return '***'
    return value


def _serialize_config_value(value: Any) -> str:
    """配置值入库序列化。

    字符串原样入库（与历史数据保持一致）；bool/None/数字/容器统一走 JSON，
    保证读回时能恢复原始类型。JSON 无法表达的类型退回 str() 兼容。
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _deserialize_config_value(value: Any) -> Any:
    """配置值读回反序列化，与 _serialize_config_value 对称。

    对字符串先尝试 JSON 解析；失败时做旧数据兼容——历史版本用 str() 直接入库，
    会产生 "True"/"False"/"None" 字面量，这里还原为对应类型。
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

    stripped = value.lstrip()
    # 只对可能构成 JSON 的开头字符做解析尝试，避免对普通文本反复抛异常
    if stripped[:1] in ('{', '[', '"', 't', 'f', 'n', '-',
                        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'):
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            pass
    return value


def coerce_bool(value: Any, default: bool = False) -> bool:
    """统一的布尔配置解析入口。

    新配置经 _deserialize_config_value 后已是 bool，直接返回；
    兼容处理历史字符串与宽松写法（1/yes/on/t/y 等）。
    无法识别的非空字符串返回 default。
    """
    if value is None or value is _MISSING:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('1', 'true', 'yes', 'on', 't', 'y'):
            return True
        # 空串按既有约定（_get_bool / _coerce_bool）视为 False
        if normalized in ('', '0', 'false', 'no', 'off', 'n'):
            return False
    return default


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        # _loaded 区分"库里确实没有配置"和"还没加载过"，避免空库时每次 get 都全表查询
        self._loaded = False
        self._lock = threading.RLock()
        self._app = None
        # 延迟加载配置，避免在应用上下文外初始化
        # self._load_configs()

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
                logger.debug(f"加载了 {len(rows)} 个配置项")
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            if not self._loaded:
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
                self._load_configs()
            return {k: v for k, v in self._cache.items() if v is not _MISSING}

    def get_cache_snapshot(self) -> Dict[str, Any]:
        """诊断用：返回缓存原始快照，负缓存哨兵显示为 None。"""
        with self._lock:
            return {k: (None if v is _MISSING else v) for k, v in self._cache.items()}

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

                # 更新缓存（存原始值，与读回反序列化结果一致）
                with self._lock:
                    self._cache[key] = value

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
        """批量更新配置"""
        try:
            for key, value in configs.items():
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

    def set_google_sheet_config(self, config: Dict[str, Any]) -> bool:
        """设置Google Sheet相关配置"""
        try:
            for key, value in config.items():
                self.set_config(key, value)
            # 强制刷新缓存
            self.refresh_cache()
            return True
        except Exception as e:
            logger.error(f"设置Google Sheet配置失败: {str(e)}")
            return False

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
