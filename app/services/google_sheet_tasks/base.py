import calendar
# stdlib json 仅保留 allow_nan=False 的 NaN/Inf 守卫用途（orjson 会静默序列化为
# null，无法等价表达，见 app/utils/json_utils.py）；其余统一走 json_utils。
import json
from app.utils.json_utils import dumps, loads, JSONDecodeError
from concurrent.futures import ThreadPoolExecutor
import random
import re
import threading
import time
from typing import Any, Dict, Optional

from flask import current_app, has_app_context
from tenacity import retry, stop_after_attempt, wait_exponential

from app.repositories import task_log_repository, task_repository, task_result_repository
from app.models import TaskLog, TaskStatus
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.services.google_sheet_tasks.kline_prep import project_and_validate_write_ready
from app.services.kline_service import KlineService, get_kline_price_field
from app.services.stock_metadata_service import upsert_stock_metadata_in_session
from app.services.task_kline_snapshot_service import (
    SnapshotLazyKlineMap,
    task_kline_snapshot_service,
)
from app.utils.db_retry import safe_db_operation
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_stock_api import StockAPIClient
from app.utils.kline_validation import require_kline_rows
from app.utils.market import infer_market_type, normalize_stock_code
from app.utils.formatting import sanitize_json_value
from app.utils.value_parser import parse_int
from app.utils.return_series import build_return_series_fields, extract_return_rows
from app.utils.logger import get_logger
from app.services.task.error_handling import (
    format_task_error_message,
    record_task_exception,
    summarize_task_exception,
)
from app.utils.task_error_utils import RetryableNetworkTaskError, is_retryable_network_error, unwrap_exception
from app.exceptions import ValidationError
from app.exceptions.sheet_check_error import SheetCheckError


logger = get_logger(__name__)

DEFAULT_EXECUTION_DELAY_MIN = 20
DEFAULT_EXECUTION_DELAY_MAX = 30
MIN_KLINE_ROWS_CONFIG_KEY = 'min_kline_rows'
DEFAULT_MIN_KLINE_ROWS = 30
DEFAULT_C3_MIN_KLINE_ROWS = 100
DEFAULT_MULTI_PRODUCT_MIN_KLINE_ROWS = 100
DEFAULT_SHEET_SETTLE_SECONDS = 20
MAX_SHEET_SETTLE_SECONDS = 300
DEFAULT_SHEET_REFRESH_INTERVAL = 10
DEFAULT_SHEET_REFRESH_ATTEMPTS = (5, 15, 25, 35)
POLL_ATTEMPT_LIMIT = 60

# random_price 随机序列模式：per_window 各窗口独立播种（现状默认，seed 含窗口键）；
# full_truncate 全区间生成一次、各窗口按日期截断切片（seed 用全区间窗口键，
# 同组号跨窗口共享同一条逻辑随机序列）。
RANDOM_SERIES_MODE_PER_WINDOW = "per_window"
RANDOM_SERIES_MODE_FULL_TRUNCATE = "full_truncate"
RANDOM_SERIES_MODES = (RANDOM_SERIES_MODE_PER_WINDOW, RANDOM_SERIES_MODE_FULL_TRUNCATE)


def normalize_random_series_mode(value) -> str:
    """随机序列模式归一化：空值回落 per_window，非法值报错。"""
    mode = str(value or RANDOM_SERIES_MODE_PER_WINDOW).strip().lower()
    if mode not in RANDOM_SERIES_MODES:
        raise ValueError(
            "随机序列模式仅支持 per_window（各窗口独立随机）或 full_truncate（全区间生成后截断）"
        )
    return mode


def should_alert_execute_task_result(result):
    return result == 'error'


def _shift_date_months(date_str, months):
    """ISO 日期字符串按月平移（months 可为负），日超过目标月天数时钳制到月末。"""
    year = int(date_str[:4])
    month = int(date_str[5:7])
    total = year * 12 + (month - 1) + months
    last_day = calendar.monthrange(total // 12, total % 12 + 1)[1]
    day = min(int(date_str[8:10]), last_day)
    return f"{total // 12:04d}-{total % 12 + 1:02d}-{day:02d}"


def parse_range_start(range_a1: str) -> tuple[str, int]:
    """解析 A1 范围的起始单元格，返回 (列字母, 起始行号)；非法范围抛 ValueError。"""
    match = re.match(r"^([A-Z]+)(\d+)", str(range_a1 or "").upper())
    if not match:
        raise ValueError(f"无效的结果范围: {range_a1}")
    return match.group(1), int(match.group(2))


def calculate_index_returns_from_closes(kline_rows) -> list[float]:
    """以真实收盘价计算相对首日的累计指数收益（C7.0.3/C1.1 共用）。"""
    base_close = None
    index_returns = []

    for index, row in enumerate(kline_rows, start=1):
        try:
            close_price = float(row["close"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"K线第 {index} 条收盘价无效") from error
        if close_price <= 0:
            raise ValueError(f"K线第 {index} 条收盘价必须大于 0")

        if base_close is None:
            base_close = close_price
        index_returns.append(close_price / base_close - 1)

    return index_returns


def resolve_min_kline_rows(default: int = DEFAULT_MIN_KLINE_ROWS, log_warning=None) -> int:
    """K线最小条数统一配置；留空或非法时回退到调用方默认值。"""
    raw_value = get_config_manager().get_config(MIN_KLINE_ROWS_CONFIG_KEY, None)
    if raw_value in (None, ''):
        return default

    min_rows = parse_int(raw_value, default=None)
    if min_rows is None or min_rows < 1:
        message = f"K线最小条数配置无效（{raw_value!r}），使用默认值 {default}"
        if log_warning:
            log_warning(message)
        else:
            logger.warning(message)
        return default
    return min_rows


def build_execute_task_alert(target, func_name, phase, exc, result):
    if exc is not None:
        return f"{func_name} 执行异常: {type(exc).__name__}: {exc}"

    task = getattr(target, 'task', None)
    task_error = getattr(task, 'error', None)
    if task_error:
        return f"{func_name} 返回失败状态: {result}, 错误信息: {task_error}"
    return f"{func_name} 返回失败状态: {result}"


class BaseGoogleSheetService:
    _model_version = ""
    # 日志缓冲刷新边界：条数/时间双阈值 + error 级立即刷。
    # 最长 10 秒延迟远低于看门狗 last_write_time 判卡死阈值（默认 watchdog_log_timeout_minutes=30 分钟）。
    _LOG_FLUSH_BATCH_SIZE = 20
    _LOG_FLUSH_INTERVAL_SECONDS = 10

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        self.config = config
        self.task_id = task_id
        self.app = app
        self.stop_event = stop_event
        self.task_name = ''
        self.task = None
        self.task_logger = get_logger(f"{self.__module__}.{task_id}")
        self.api_client = StockAPIClient()
        # 日志批量落库缓冲（见 _save_to_database；任务线程独享，锁只防收尾 flush 并发）
        self._log_buffer = []
        self._log_buffer_lock = threading.Lock()
        self._log_last_flush_monotonic = time.monotonic()

    def _normalize_result_parameters(self, parameters: Any) -> dict[str, Any]:
        """Ensure persisted result parameters always contain stock_code."""
        safe = sanitize_json_value(parameters)
        normalized = dict(safe) if isinstance(safe, dict) else {"parameters": safe}
        stock_code = (
            normalized.get("stock_code")
            or normalized.get("stock_no")
            or normalized.get("symbol")
            or (self.config or {}).get("stock_code")
        )
        if not stock_code and self.task and self.task.config:
            try:
                task_config = (
                    self.task.config
                    if isinstance(self.task.config, dict)
                    else loads(self.task.config)
                )
                stock_code = task_config.get("stock_code") if isinstance(task_config, dict) else None
            except (TypeError, ValueError):
                stock_code = None
        effective_market = normalized.get("market_type") or self._get_return_series_market_type(normalized)
        normalized["stock_code"] = normalize_stock_code(
            stock_code,
            effective_market or infer_market_type(stock_code),
            normalized.get("exchange_market") or self._get_return_series_exchange_market(normalized),
        )
        return normalized

    def _get_return_series_market_type(self, parameters: Any):
        """优先使用参数中的市场代码，缺失时回退到任务配置。"""
        return self._get_return_series_config_value(parameters, "market_type")

    def _get_return_series_exchange_market(self, parameters: Any):
        """获取 Yahoo ticker 所需的交易所市场编号。"""
        return self._get_return_series_config_value(parameters, "exchange_market")

    def _get_return_series_config_value(self, parameters: Any, key: str):
        if isinstance(parameters, dict) and parameters.get(key):
            return parameters[key]
        if isinstance(self.config, dict) and self.config.get(key):
            return self.config[key]
        if self.task and self.task.config:
            try:
                task_config = (
                    self.task.config
                    if isinstance(self.task.config, dict)
                    else loads(self.task.config)
                )
                if isinstance(task_config, dict):
                    return task_config.get(key)
            except (TypeError, ValueError):
                pass
        return None


    def _is_cancel_requested(self) -> bool:
        if self.stop_event and self.stop_event.is_set():
            return True
        try:
            task = task_repository.get_entity(self.task_id)
            return bool(task and task.status == TaskStatus.CANCELLED.value)
        except Exception:
            return False

    def _interruptible_sleep(self, seconds: float) -> bool:
        if seconds <= 0:
            return not self._is_cancel_requested()
        if self.stop_event:
            return not self.stop_event.wait(seconds)
        import time
        time.sleep(seconds)
        return not self._is_cancel_requested()

    def _get_execution_poll_delay_bounds(self) -> tuple[int, int]:
        try:
            config_manager = get_config_manager()
            delay_min = int(config_manager.get_config('execution_delay_min', DEFAULT_EXECUTION_DELAY_MIN))
            delay_max = int(config_manager.get_config('execution_delay_max', DEFAULT_EXECUTION_DELAY_MAX))
        except (TypeError, ValueError) as exc:
            self._log_warning(f"执行等待配置无效，使用默认值 20-30 秒: {exc}")
            return DEFAULT_EXECUTION_DELAY_MIN, DEFAULT_EXECUTION_DELAY_MAX

        if delay_min < 0 or delay_max < 0 or delay_min > delay_max:
            self._log_warning(
                f"执行等待配置无效，使用默认值 20-30 秒: min={delay_min}, max={delay_max}"
            )
            return DEFAULT_EXECUTION_DELAY_MIN, DEFAULT_EXECUTION_DELAY_MAX

        return delay_min, delay_max

    @staticmethod
    def _get_execution_poll_delay(attempt: int, delay_min: int, delay_max: int) -> int:
        return int(min(delay_min + max(attempt, 0) * 5, delay_max))

    def _get_min_kline_rows(self, default: int = DEFAULT_MIN_KLINE_ROWS) -> int:
        return resolve_min_kline_rows(default, log_warning=self._log_warning)

    def _get_sheet_settle_seconds(self) -> int:
        try:
            settle_seconds = int(
                get_config_manager().get_config(
                    'sheet_settle_seconds', DEFAULT_SHEET_SETTLE_SECONDS
                )
            )
        except (TypeError, ValueError) as exc:
            self._log_warning(
                f"Sheet 等待配置无效，使用默认值 {DEFAULT_SHEET_SETTLE_SECONDS} 秒: {exc}"
            )
            return DEFAULT_SHEET_SETTLE_SECONDS

        if settle_seconds < 0 or settle_seconds > MAX_SHEET_SETTLE_SECONDS:
            self._log_warning(
                f"Sheet 等待配置无效，使用默认值 {DEFAULT_SHEET_SETTLE_SECONDS} 秒: {settle_seconds}"
            )
            return DEFAULT_SHEET_SETTLE_SECONDS
        return settle_seconds

    def _get_refresh_interval(self) -> int:
        try:
            interval = int(
                get_config_manager().get_config(
                    'sheet_refresh_interval_attempts', DEFAULT_SHEET_REFRESH_INTERVAL
                )
            )
        except (TypeError, ValueError) as exc:
            self._log_warning(
                f"刷新间隔配置无效，使用默认值 {DEFAULT_SHEET_REFRESH_INTERVAL}: {exc}"
            )
            return DEFAULT_SHEET_REFRESH_INTERVAL

        if interval < 0 or interval >= POLL_ATTEMPT_LIMIT:
            self._log_warning(
                f"刷新间隔配置无效，使用默认值 {DEFAULT_SHEET_REFRESH_INTERVAL}: {interval}"
            )
            return DEFAULT_SHEET_REFRESH_INTERVAL
        return interval

    @staticmethod
    def _coerce_refresh_attempts(value) -> frozenset[int]:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return frozenset()
            try:
                value = loads(text)
            except (TypeError, ValueError):
                value = [part.strip() for part in text.split(',') if part.strip()]

        if not isinstance(value, (list, tuple)):
            raise ValueError(f"刷新轮次必须是数组: {value!r}")

        attempts = set()
        for item in value:
            attempt = int(item)
            if attempt < 1 or attempt >= POLL_ATTEMPT_LIMIT:
                raise ValueError(f"刷新轮次必须在 1-{POLL_ATTEMPT_LIMIT - 1} 之间: {attempt}")
            attempts.add(attempt)
        return frozenset(attempts)

    def _get_refresh_attempts(self) -> frozenset[int]:
        try:
            value = get_config_manager().get_config(
                'sheet_refresh_attempts', list(DEFAULT_SHEET_REFRESH_ATTEMPTS)
            )
            return self._coerce_refresh_attempts(value)
        except (TypeError, ValueError) as exc:
            self._log_warning(
                f"刷新轮次配置无效，使用默认值 {list(DEFAULT_SHEET_REFRESH_ATTEMPTS)}: {exc}"
            )
            return frozenset(DEFAULT_SHEET_REFRESH_ATTEMPTS)

    def _get_poll_refresh_settings(self) -> tuple[int, frozenset[int]]:
        return self._get_refresh_interval(), self._get_refresh_attempts()

    def _poll_google_sheet_completion(self, attempt_fn, refresh_fn=None, post_attempt_fn=None, timeout_payload=(False, {})):
        """C 系参数组合轮询骨架（ponytail 审计 B3 上提，c3/c4/c5/c7/training 共用）。

        - refresh_fn(settle)：可选的防卡顿参数刷新，在
          sheet_refresh_attempts / 每 sheet_refresh_interval_attempts 次
          （且非首轮）的检查**之前**触发；C3/C5/C7/training 共用同一套刷新策略；
          settle 读 sheet_settle_seconds；
        - post_attempt_fn(attempt)：检查之后触发的钩子（c4 用于配置的刷新轮次
          重写参数+重快照，其内部自带 30s 等待）；
        - attempt_fn(attempt) → (是否全部完成, 结果载荷)；完成与未完成的
          业务日志由 attempt_fn 自行输出；
        - 超过 POLL_ATTEMPT_LIMIT 次未完成返回 timeout_payload（c5/c7/c4 为 (False, {})，
          training 为 (False, {}, [])）。
        """
        delay_min, delay_max = self._get_execution_poll_delay_bounds()
        refresh_interval, refresh_attempts = self._get_poll_refresh_settings()
        settle_seconds = self._get_sheet_settle_seconds() if refresh_fn is not None else 0
        for attempt in range(POLL_ATTEMPT_LIMIT):
            # 定期刷新参数，防止模型卡顿
            if refresh_fn is not None and attempt != 0 and (
                (refresh_interval > 0 and attempt % refresh_interval == 0)
                or attempt in refresh_attempts
            ):
                self._log_info("刷新参数")
                refresh_fn(settle_seconds)

            _ = self._get_execution_poll_delay(attempt, delay_min, delay_max)
            self._log_info(f"第 {attempt + 1} 次检查执行状态... delay {_} 秒")
            if not self._interruptible_sleep(_):
                raise RuntimeError("task cancelled")
            done, payload = attempt_fn(attempt)
            if done:
                return True, payload
            if post_attempt_fn is not None and attempt in refresh_attempts:
                post_attempt_fn(attempt)
        self._log_warning("执行超时，未在规定时间内完成")
        return timeout_payload

    def _task_detail_url(self) -> str:
        return f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}"

    def task_ok_to_dd(self, result):
        payload_result = self.app.notifier.send_task_notification(
            self.task_id,
            notify_type="success",
            summary=result,
            detail_url=self._task_detail_url(),
        )
        return payload_result

    def _log(self, level: str, message: str, log_type: str = 'general', **kwargs):
        try:
            formatted_message = self._format_log_message(message, log_type, **kwargs)
            prefixed_message = f"[Task-{self.task_id[:8]}] {formatted_message}"

            if level == 'error':
                self.task_logger.error(prefixed_message)
            elif level == 'warning':
                self.task_logger.warning(prefixed_message)
            else:
                self.task_logger.info(prefixed_message)

            self._save_to_database(level, formatted_message)
        except Exception:
            pass

    def _format_log_message(self, message: str, log_type: str, **kwargs) -> str:
        if log_type == 'step':
            step = kwargs.get('step', 0)
            total = kwargs.get('total', 0)
            return f"[Step {step}/{total}] {message}"
        if log_type == 'api_error':
            action = kwargs.get('action', '')
            error = kwargs.get('error', '')
            return f"[API_ERROR] {action} - {error}"
        return message

    def _save_to_database(self, level: str, message: str):
        # 组合热路径每组合产生多条日志，逐条 INSERT+COMMIT 是任务时长的主要 DB 开销；
        # 缓冲定量/定时合并为一次事务提交（error 级立即落库）。
        with self._log_buffer_lock:
            self._log_buffer.append((level, message))
            should_flush = (
                level == 'error'
                or len(self._log_buffer) >= self._LOG_FLUSH_BATCH_SIZE
                or (time.monotonic() - self._log_last_flush_monotonic)
                >= self._LOG_FLUSH_INTERVAL_SECONDS
            )
            if not should_flush:
                return
            pending = self._log_buffer[:]
            self._log_buffer.clear()
            self._log_last_flush_monotonic = time.monotonic()
        self._flush_log_buffer(pending)

    def _flush_log_buffer(self, pending=None):
        """把缓冲日志（缺省取全部未刷日志）合并为一次事务提交；吞掉异常不向调用方传播。"""
        if pending is None:
            with self._log_buffer_lock:
                pending = self._log_buffer[:]
                self._log_buffer.clear()
                self._log_last_flush_monotonic = time.monotonic()
        if not pending:
            return

        def save_logs_operation():
            for level, message in pending:
                task_log_repository.add_entity(
                    TaskLog(
                        task_id=self.task_id,
                        level=level,
                        message=TaskLog.normalize_message(message),
                    )
                )
            task_result_repository.commit()

        try:
            if has_app_context():
                safe_db_operation(save_logs_operation)
            elif self.app:
                with self.app.app_context():
                    safe_db_operation(save_logs_operation)
            else:
                with current_app.app_context():
                    safe_db_operation(save_logs_operation)
        except Exception:
            # 提交失败后 SQLAlchemy session 会处于 failed state；必须回滚，
            # 否则后续任务结果写入会触发 PendingRollbackError。
            try:
                task_result_repository.rollback()
            except Exception:
                pass

    def _summarize_result_for_log(self, result: Any) -> str:
        """返回不包含收益序列的短结果摘要，避免将大对象写入任务日志。"""
        if not isinstance(result, dict):
            return str(result)[:1000]

        summary = {}
        for key, value in result.items():
            if key in {"_return_date", "return_date", "returns_json"}:
                continue
            if isinstance(value, (list, tuple, dict)):
                summary[key] = f"<{type(value).__name__}, len={len(value)}>"
            else:
                summary[key] = value
        return dumps(
            sanitize_json_value(summary),
            ensure_ascii=False,
            default=str,
        )[:1000]

    @classmethod
    def _prepare_result_for_persistence(cls, result: Any):
        """移除已单独保存到 TaskResultReturn 的收益明细，保留结果指标。"""
        if isinstance(result, dict):
            return {
                key: cls._prepare_result_for_persistence(value)
                for key, value in result.items()
                if key not in {"_return_date", "return_date", "returns_json"}
            }
        if isinstance(result, list):
            return [cls._prepare_result_for_persistence(value) for value in result]
        if isinstance(result, tuple):
            return [cls._prepare_result_for_persistence(value) for value in result]
        return result

    def _build_task_result_persistence_payload(
        self, safe_parameters: dict[str, Any], result: Any, return_date=None
    ):
        """持久化前的结果载荷整形钩子；默认透传，子类按需重写。

        注意：BacktestMultiProductService 重写本钩子以叠加加权组合指标，
        不能作为死代码删除。
        """
        return result

    def _get_return_series_stock_name(self, safe_parameters: dict[str, Any]):
        """收益序列 stock_name 取值钩子；子类可重写以增加回退字段。"""
        return safe_parameters.get("stock_name")


    # ---- 断点/去重公共件（原 C5/C7 逐字或近逐字复制，C3 批次收敛）----

    # 去重日志中的任务标签；子类按需覆盖。
    _dedupe_label = "C"

    @staticmethod
    def _get_resume_start_index(current_step: int | None, total_combinations: int) -> int:
        """返回下一条待执行组合的下标（current_step 为已完成组合数）。"""
        return min(max(int(current_step or 0), 0), total_combinations)

    def _dedupe_extra_signature(self, combination: dict) -> tuple:
        """去重签名的任务特定附加字段；默认无附加。"""
        return ()

    @staticmethod
    def _resolve_kline_signature(kline_data_map, kline_key):
        """窗口签名 (首日, 末日, 行数)；惰性映射读登记元数据，普通映射物化行。"""
        signature_getter = getattr(kline_data_map, "kline_signature", None)
        if signature_getter is not None:
            return signature_getter(kline_key)
        kline = kline_data_map.get(kline_key)
        if not kline:
            return None
        return (
            kline[0].get('stock_date'),
            kline[-1].get('stock_date'),
            len(kline),
        )

    def _deduplicate_parameter_combinations(self, combinations, kline_data_map):
        """按股票、参数和实际K线区间去除重复回测组合。"""
        deduplicated = []
        seen = set()
        for combination in combinations:
            kline_signature = self._resolve_kline_signature(
                kline_data_map, combination.get('kline_key')
            )
            if kline_signature is None:
                deduplicated.append(combination)
                continue

            signature = (
                str(combination.get('stock_code', '')),
                str(combination.get('A1', '')),
                str(combination.get('B1', '')),
                kline_signature,
                *self._dedupe_extra_signature(combination),
            )
            if signature in seen:
                self._log_info(
                    f"跳过重复 {self._dedupe_label} 参数组合："
                    f"股票={combination.get('stock_code', '')}，"
                    f"A1={combination.get('A1', '')}，B1={combination.get('B1', '')}，"
                    f"K线区间={kline_signature[0]}~{kline_signature[1]}，"
                    f"行数={kline_signature[2]}"
                )
                continue

            seen.add(signature)
            deduplicated.append(combination)

        return deduplicated


    def _raise_retryable_network_error(self, exc, context):
        """网络类异常统一打可重试标记（原 C7 实现上移；供 get_bdl/子类复用）。"""
        if is_retryable_network_error(exc):
            root = unwrap_exception(exc) or exc
            raise RetryableNetworkTaskError(f"{context}: {root}") from exc

    # ---- get_bdl 批量执行钩子（C3 批次差异地图见 03 文档 §3.3；默认实现 = C5 行为）----

    # 外层异常是否打 [NETWORK_RETRYABLE] 标记（C7 = True；C5 默认无）。
    _retryable_outer = False

    # 随机价展开时是否落 K 线快照；组合数精算置 False（估算不是任务执行）。
    _persist_random_snapshots = True

    def _load_custom_kline_map(self, config_data: dict) -> dict:
        """custom K线读取钩子（C5 默认：固定 c5 A/B 输入列；C7 覆盖为布局驱动）。"""
        c5_input_column_a = config_data.get('c5_input_column_a').upper()
        c5_input_column_b = config_data.get('c5_input_column_b').upper()
        custom_kline = self._get_custom_kline_data(c5_input_column_a, c5_input_column_b)
        return {'custom': custom_kline}

    def _prepare_batch(self, config_data: dict) -> dict:
        """从任务配置提取批量执行所需的标量与自定义K线映射（C5 默认实现）。"""
        kline_source = str(config_data.get('kline_source') or 'auto').strip().lower()
        if kline_source not in ('auto', 'custom'):
            raise ValueError("kline_source 仅支持 auto 或 custom")
        custom_kline_map = None
        if kline_source == 'custom':
            custom_kline_map = self._load_custom_kline_map(config_data)
        return {
            "kline_source": kline_source,
            "count_mode": config_data.get('count_mode', 'n_plus_1'),
            "price_mode": config_data.get('price_mode', 'vwap_price'),
            "date_range_mode": config_data.get('date_range_mode', []),
            "exclude_recent_years": config_data.get(
                'exclude_recent_years',
                config_data.get('exclude_years', []),
            ),
            "end_date": config_data.get('end_date'),
            "start_date": config_data.get('start_date'),
            "market_type": config_data.get('market_type'),
            "adjust_type": config_data.get('kline_adjustment'),
            "data_source": config_data.get("kline_data_source", "akshare"),
            "custom_kline_map": custom_kline_map,
            "random_price_range": config_data.get('random_price_range', 'high_low'),
            "random_group_count": int(config_data.get('random_group_count') or 1),
            "random_series_mode": normalize_random_series_mode(
                config_data.get('random_series_mode')
            ),
        }

    def _expand_parameters(self, outer_param, parameters, batch):
        """单外层参数 → (组合列表, A列长度, kline_data_map)；默认走 C5 签名。"""
        return self._get_all_parameters(
            outer_param,
            batch["count_mode"],
            batch["price_mode"],
            batch["end_date"],
            batch["start_date"],
            batch["market_type"],
            batch["date_range_mode"],
            batch["exclude_recent_years"],
            parameters,
            batch["adjust_type"],
            data_source=batch["data_source"],
            random_price_range=batch["random_price_range"],
            random_group_count=batch["random_group_count"],
            random_series_mode=batch["random_series_mode"],
        )

    def _get_precompute_concurrency(self) -> int:
        """K线预计算并行度（SystemConfig kline_precompute_concurrency，0/1=串行）。

        默认 4、上限 16；外部行情源（东财/Yahoo）存在限流风险，调高前确认配额。
        """
        try:
            config_manager = get_config_manager()
            value = int(config_manager.get_config('kline_precompute_concurrency', 4))
        except (TypeError, ValueError):
            return 4
        return max(0, min(value, 16))

    def _expand_all_outer_parameters(self, batch, parameters):
        """外层参数（多股票）预计算展开，返回 [(combinations, column_A_length, kline_data_map)]。

        并行度 >1 且多股票时用有界线程池：每股在独立服务实例上展开——
        KlineService 持有 requests.Session 与内部K线库客户端，非线程安全不能跨线程共享；
        并各自推独立 app context（随机价快照落库、股票元数据 upsert 依赖 per-thread
        session，Flask-SQLAlchemy 3.x 随 context 弹出回收）。任一股票失败按原顺序
        抛出第一个异常，与串行语义一致。
        """
        outer_params = list(parameters[0])

        def expand(index):
            outer_param = outer_params[index]
            if batch["kline_source"] == 'custom':
                return self._get_custom_parameters(outer_param, parameters, batch["custom_kline_map"])
            return self._expand_parameters(outer_param, parameters, batch)

        concurrency = self._get_precompute_concurrency()
        if batch["kline_source"] == 'custom' or concurrency <= 1 or len(outer_params) <= 1:
            return [expand(index) for index in range(len(outer_params))]

        context_app = self.app or current_app
        workers: Dict[int, "BaseGoogleSheetService"] = {}
        workers_lock = threading.Lock()

        def run_at(index):
            ident = threading.get_ident()
            with workers_lock:
                worker = workers.get(ident)
                if worker is None:
                    # 构造必须在 app context 内：KlineService/StockAPIClient 在
                    # __init__ 读 current_app.config（STOCK_BASE_URL 等），
                    # 线程无上下文时会静默落到 SDK 默认地址
                    with context_app.app_context():
                        worker = type(self)(self.config, self.task_id, app=self.app, stop_event=self.stop_event)
                    workers[ident] = worker
            with context_app.app_context():
                return worker._expand_parameters(outer_params[index], parameters, batch)

        results = [None] * len(outer_params)
        first_error = None
        executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="kline-precompute")
        try:
            futures = {index: executor.submit(run_at, index) for index in range(len(outer_params))}
            for index in sorted(futures):
                try:
                    results[index] = futures[index].result()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
        finally:
            executor.shutdown(wait=True)
            # 回收各 worker 独立缓冲的任务日志（worker 自身不再被使用）
            for worker in workers.values():
                worker._flush_log_buffer()

        if first_error is not None:
            raise first_error
        return results

    def _get_custom_parameters(self, parameter, parameters, custom_kline_map, *, deduplicate: bool = True):
        """custom K线模式的固定双参数组合（原 C5/C7 各持一份，仅去重差异经参数表达）。

        C5 传入 deduplicate=True（组合对 K线窗口去重）；C7 传 False 保持原行为。
        基类 get_bdl 调用不显式传 deduplicate，默认 True（窗口去重为安全缺省）。
        """
        data = []
        for v1 in parameters[1]:
            for v2 in parameters[2]:
                data.append({
                    "stock_code": parameter,
                    "A1": v1,
                    "B1": v2,
                    "kline_key": "custom",
                })

        if not data:
            raise ValueError(f"股票{parameter} 自定义K线模式下没有可执行参数组合")

        if deduplicate:
            data = self._deduplicate_parameter_combinations(data, custom_kline_map)
        return data, len(custom_kline_map["custom"]) + 20, custom_kline_map

    def _expand_random_price_groups(
        self,
        combinations,
        kline_data_map,
        price_mode,
        random_price_range,
        random_group_count,
        snapshot_meta=None,
        random_series_mode=RANDOM_SERIES_MODE_PER_WINDOW,
        full_kline=None,
        full_kline_key=None,
    ):
        """random_price 模式下按组数展开组合；每组用 task_id 播种的确定性随机序列重取价格。

        有 Flask app context 且传入 snapshot_meta 时落库并复用随机K线快照；
        返回的 kline 映射为 SnapshotLazyKlineMap（只登记 series id 与窗口签名，
        行列表执行期按需物化），避免全任务驻留全部合并行；
        纯生成单测无上下文时保留原内存路径，不写库。

        random_series_mode=per_window（默认）：seed 含窗口键，各窗口独立摇序列（现状）。
        random_series_mode=full_truncate：seed 用 full_kline_key（全区间窗口键）在全区间
        K线上生成一次，再按当前窗口首末日期截取切片——同组号跨窗口共享同一条逻辑序列，
        各窗口的 series 仍按各自 kline_key 落库（值为切片，seed 相同）。
        """
        if price_mode != "random_price":
            return combinations, kline_data_map
        full_truncate = random_series_mode == RANDOM_SERIES_MODE_FULL_TRUNCATE
        if full_truncate and (not full_kline or not full_kline_key):
            raise ValueError("全区间截断模式需要全区间K线与窗口键")
        persist_snapshots = (
            snapshot_meta is not None
            and has_app_context()
            and self._persist_random_snapshots
        )
        grouped_data = []
        if persist_snapshots:
            # 持久路径不物化合并行：只登记 series id，行列表执行期从快照表按需拼回
            grouped_map: Any = SnapshotLazyKlineMap(
                task_kline_snapshot_service.materialize_series_rows
            )
        else:
            grouped_map = {}
        group_series_ids = {}
        sources_by_key = {}
        full_rows_by_group = {}
        for combination in combinations:
            source_key = combination["kline_key"]
            source_kline = kline_data_map[source_key]
            stock_code = str(combination.get("stock_code") or "").strip()
            source = None
            if persist_snapshots:
                source_cache_key = (stock_code, source_key)
                if source_cache_key not in sources_by_key:
                    sources_by_key[source_cache_key] = (
                        task_kline_snapshot_service.get_or_create_source(
                            task_id=self.task_id,
                            stock_code=stock_code,
                            stock_name=(
                                snapshot_meta.get("stock_name")
                                or combination.get("stock_name")
                            ),
                            market_type=snapshot_meta.get("market_type"),
                            kline_key=source_key,
                            data_source=snapshot_meta.get("data_source"),
                            adjust_type=snapshot_meta.get("adjust_type"),
                            rows=source_kline,
                        )
                    )
                source = sources_by_key[source_cache_key]
            for random_group in range(1, int(random_group_count or 1) + 1):
                group_key = f"{source_key}:random-{random_group}"
                if group_key not in grouped_map:
                    # full_truncate 的播种基准是全区间窗口键，与具体窗口无关
                    seed_key = full_kline_key if full_truncate else source_key
                    seed = (
                        f"{self.task_id}:{stock_code}:"
                        f"{seed_key}:{random_price_range}:{random_group}"
                    )
                    if full_truncate:
                        group_cache_key = (stock_code, random_group)
                        if group_cache_key not in full_rows_by_group:
                            full_rows_by_group[group_cache_key] = (
                                KlineService.build_price_rows(
                                    full_kline,
                                    price_mode,
                                    include_ohlc=True,
                                    random_price_range=random_price_range,
                                    random_generator=random.Random(seed),
                                )
                            )
                        window_rows = self._slice_random_rows_by_window(
                            full_rows_by_group[group_cache_key], source_kline
                        )
                        if persist_snapshots:
                            series = task_kline_snapshot_service.get_or_create_series(
                                source=source,
                                task_id=self.task_id,
                                stock_code=stock_code,
                                kline_key=source_key,
                                random_group=random_group,
                                price_mode=price_mode,
                                random_price_range=random_price_range,
                                seed=seed,
                                rows=source_kline,
                                values=[row["stock_val"] for row in window_rows],
                            )
                            grouped_map.register(
                                group_key,
                                series["id"],
                                start_date=source["start_date"],
                                end_date=source["end_date"],
                                row_count=int(source.get("row_count") or 0),
                            )
                            group_series_ids[group_key] = series["id"]
                        else:
                            grouped_map[group_key] = window_rows
                    elif persist_snapshots:
                        series = task_kline_snapshot_service.get_or_create_series(
                            source=source,
                            task_id=self.task_id,
                            stock_code=stock_code,
                            kline_key=source_key,
                            random_group=random_group,
                            price_mode=price_mode,
                            random_price_range=random_price_range,
                            seed=seed,
                            rows=source_kline,
                        )
                        grouped_map.register(
                            group_key,
                            series["id"],
                            start_date=source["start_date"],
                            end_date=source["end_date"],
                            row_count=int(source.get("row_count") or 0),
                        )
                        group_series_ids[group_key] = series["id"]
                    else:
                        random_generator = random.Random(seed)
                        grouped_map[group_key] = KlineService.build_price_rows(
                            source_kline,
                            price_mode,
                            include_ohlc=True,
                            random_price_range=random_price_range,
                            random_generator=random_generator,
                        )
                item = dict(combination)
                item["kline_key"] = group_key
                item["random_group"] = random_group
                if persist_snapshots:
                    item["kline_series_id"] = group_series_ids[group_key]
                grouped_data.append(item)
        return grouped_data, grouped_map

    @staticmethod
    def _slice_random_rows_by_window(full_rows, window_kline):
        """全区间随机序列行按窗口K线首末日期截取切片；行数必须与窗口K线一致。"""
        start_date = window_kline[0]["stock_date"]
        end_date = window_kline[-1]["stock_date"]
        rows = [
            row for row in full_rows
            if start_date <= row["stock_date"] <= end_date
        ]
        if len(rows) != len(window_kline):
            raise ValueError(
                f"全区间随机序列切片行数 {len(rows)} 与窗口K线行数 {len(window_kline)} 不一致，"
                f"窗口 {start_date}~{end_date}"
            )
        return rows

    def _expand_auto_year_parameters(
        self,
        parameter,
        count_mode,
        price_mode,
        end_date,
        start_date,
        market_type,
        date_range_mode,
        exclude_recent_years,
        parameters,
        adjust_type=None,
        data_source="akshare",
        source_label="google_sheet",
        include_ohlc=False,
        random_price_range="high_low",
        random_group_count=1,
        random_series_mode=RANDOM_SERIES_MODE_PER_WINDOW,
        include_vwap=True,
    ):
        """C5/C7 共享的 auto-K线年度参数展开骨架（ponytail 审计 B1 合并）。

        此前 c5.py / c7.py 各持有一份 ~155 行拷贝；差异经参数表达：
        - include_ohlc：C7 写回需要 OHLC 列；random_price 展开强制开启；
        - random_price_range / random_group_count：随机价格分组（C5 已同步该能力）；
        - random_series_mode：per_window 各窗口独立随机（默认）/ full_truncate
          全区间生成一次后各窗口截断切片（播种基准 = 全区间窗口键）；
        - recent 模式统一包含近半年（0.5）区间；
        - count_mode=N+1 时同样生成全区间组合（"+1"），与窗口重合时由组合去重合并。
        custom K线分支仍留在各自 service（_get_custom_parameters），不进本骨架。
        """
        # random_price 分组展开前先按收盘价占位取价；分组随机取价在 _expand_random_price_groups 里做
        projection_mode = 'sp_price' if price_mode == 'random_price' else price_mode
        if price_mode == 'random_price':
            # 随机价格展开依赖 high/low 列重建价格序列
            include_ohlc = True

        _end_year_1 = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        _end_year = int(now_time[:4])
        _start_date = int(start_date[:4])
        # 近年区间总数按用户配置区间的起点年份计算；下方K线首日截断会改写
        # _start_date，但那只收缩单个区间内的实际数据，不应减少区间数量。
        _config_start_year = _start_date
        limit = (_end_year - _start_date + 1) * 300

        klines = self.kline_service.get_kline_data(
            parameter,
            market_type,
            limit,
            data_source=data_source,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            include_vwap=include_vwap,
        )
        stock_name = str(klines[0].get("stock_name") or "") if klines else ""
        parameter = str(klines[0].get("stock_code") or parameter) if klines else parameter
        if stock_name:
            upsert_stock_metadata_in_session({
                "stock_code": parameter,
                "stock_name": stock_name,
                "market_type": market_type,
                "source": source_label,
            })

        price_field = get_kline_price_field(price_mode)
        if price_mode == 'random_price':
            # 随机价格模式的取值字段随 random_price_range 变化
            price_field = 'high' if random_price_range == 'high_low' else 'close'
        klines = require_kline_rows(
            parameter,
            market_type,
            klines,
            context="原始K线",
            min_rows=self._get_min_kline_rows(),
            price_field=price_field,
        )

        # 获取K线数据的时间范围
        data_start_date = klines[0]['stock_date']
        data_end_date = klines[-1]['stock_date']
        if start_date < data_start_date:
            self._log_info(
                f"股票{parameter} 请求起始日期 {start_date} 早于可用K线首日 {data_start_date}，"
                f"将从 {data_start_date} 开始回测"
            )
            start_date = data_start_date
            _start_date = int(start_date[:4])

        # 构建 full_years 列表（用于全年回测模式的边界检查）
        full_years = None
        if 'full' in date_range_mode:
            full_years = list(range(_start_date, _end_year_1 + 1))

        # 结束日期超出数据范围时仍保持原有校验，避免使用不完整的最新区间。
        if end_date > data_end_date:
            if full_years and int(data_start_date[:4]) in full_years:
                pass
            elif full_years and int(full_years[0]) > int(data_start_date[:4]):
                pass
            else:
                raise Exception(
                    f"股票{parameter} 设定区间 [{start_date}, {end_date}] 不在K线数据范围 [{data_start_date}, {data_end_date}] 内")

        # 外部数据源可能返回配置区间外的历史K线；从这里开始，所有后续
        # 区间拆分、写入 Sheet 和收益计算都只使用用户指定时间范围内的数据。
        all_kline = project_and_validate_write_ready(
            self.kline_service,
            parameter=parameter,
            market_type=market_type,
            klines=klines,
            price_mode=projection_mode,
            start_date=start_date,
            end_date=end_date,
            data_end_date=data_end_date,
            include_ohlc=include_ohlc,
        )
        snapshot_meta = {
            "stock_name": stock_name,
            "market_type": market_type,
            "data_source": data_source,
            "adjust_type": adjust_type,
        }
        # 全区间窗口键：full_truncate 随机序列的播种基准（与全区间组合 kline_key
        # 同源；_start_date 已按数据首日截断修正）
        full_kline_key = f'{_end_year_1}-{_start_date}'
        data = []

        kline_data_map = {}
        # N+1 与 total 都保留全区间组合（N+1 的"+1"）：整年模式 = 各年份 + 全区间，
        # 近年模式 = 各近年窗口 + 全区间；窗口与全区间完全重合时由组合去重合并。
        for i, v1 in enumerate(parameters[1]):
            for j, v2 in enumerate(parameters[2]):
                kline_key = f'{_end_year_1}-{_start_date}'
                # 'year' 与 'kline_key' 同值落盘：'year' 被 C4 kline_range 消费，'kline_key' 是 K线区间索引，均为既有契约
                d = {'stock_code': parameter, "A1": v1, "B1": v2, 'kline_key': kline_key}
                if stock_name:
                    d['stock_name'] = stock_name
                if kline_key not in kline_data_map:
                    kline_data_map[kline_key] = all_kline

                data.append(d)

        if count_mode != 'n_plus_1':
            data, kline_data_map = self._expand_random_price_groups(
                data,
                kline_data_map,
                price_mode,
                random_price_range,
                random_group_count,
                snapshot_meta=snapshot_meta,
                random_series_mode=random_series_mode,
                full_kline=all_kline,
                full_kline_key=full_kline_key,
            )
            data = self._deduplicate_parameter_combinations(data, kline_data_map)
            return data, len(all_kline) + 20,kline_data_map

        if 'recent' in date_range_mode:
            # 起止年份差就是可生成的近年区间数量；首尾年份相差 5 年时，
            # 应生成近 1 年到近 5 年，不能额外生成近 6 年的区间。
            # 用配置起点年份而非K线截断后的 _start_date，否则数据首日
            # 截断会把近3年/近5年整段区间悄悄丢掉。
            total_years = max(0, _end_year_1 - _config_start_year)
            # 近半年（0.5）排在最前，开始日期 = 结束日期往前推 6 个月
            recent_spans = [(0.5, _shift_date_months(end_date, -6))]
            recent_spans.extend(
                (year, f"{_end_year_1 - year}{end_date[4:]}")
                for year in range(1, total_years + 1)
            )
            for year, span_start in recent_spans:
                # 如果当前年份在排除列表中，跳过
                if year in exclude_recent_years:
                    continue

                _end_data = end_date
                _start_data = max(start_date, span_start)
                if _start_data > _end_data:
                    continue
                kline = self.kline_service.build_price_rows(
                    klines, projection_mode, start_date=_start_data, end_date=_end_data, include_ohlc=include_ohlc
                )
                if not kline:
                    continue
                kline_key = f"{kline[-1]['stock_date'][:4]}-{kline[0]['stock_date'][:4]}"
                existing = kline_data_map.get(kline_key)
                if existing is not None and (
                    existing[0]['stock_date'] != kline[0]['stock_date']
                    or existing[-1]['stock_date'] != kline[-1]['stock_date']
                    or len(existing) != len(kline)
                ):
                    # 键标签相同但窗口不同（同年配置下近半年 vs 全区间）：
                    # kline_data_map 按键只能存一份，后者让位，避免组合取到错误窗口。
                    self._log_info(
                        f"股票{parameter} 近年窗口 {kline_key} 与已注册窗口区间不同，"
                        f"跳过该窗口（{kline[0]['stock_date']}~{kline[-1]['stock_date']}）"
                    )
                    continue
                for i, v1 in enumerate(parameters[1]):
                    for j, v2 in enumerate(parameters[2]):
                        d = {"A1": v1, "B1": v2, 'stock_code': parameter, 'kline_key': kline_key}
                        if stock_name:
                            d['stock_name'] = stock_name
                        if kline_key not in kline_data_map:
                            kline_data_map[kline_key] = kline

                        data.append(d)

        if 'full' in date_range_mode:
            _all_kline = [k for k in klines if start_date <= k['stock_date'] <= end_date]
            for year in range(_start_date, _end_year_1 + 1):
                kline = self.kline_service.build_price_rows(_all_kline, projection_mode, year=year, include_ohlc=include_ohlc)
                kline_key = year
                if not kline:
                    continue

                for i, v1 in enumerate(parameters[1]):
                    for j, v2 in enumerate(parameters[2]):
                        d = {"A1": v1, "B1": v2, 'stock_code': parameter, 'kline_key': kline_key}
                        if stock_name:
                            d['stock_name'] = stock_name
                        if kline_key not in kline_data_map:
                            kline_data_map[kline_key] = kline

                        data.append(d)

        data, kline_data_map = self._expand_random_price_groups(
            data,
            kline_data_map,
            price_mode,
            random_price_range,
            random_group_count,
            snapshot_meta=snapshot_meta,
            random_series_mode=random_series_mode,
            full_kline=all_kline,
            full_kline_key=full_kline_key,
        )

        if not data:
            raise ValueError(
                f"股票{parameter}({market_type}) 在配置区间内没有可执行K线组合，"
                f"请检查 start_date={start_date}, end_date={end_date}, date_range_mode={date_range_mode}"
            )

        data = self._deduplicate_parameter_combinations(data, kline_data_map)
        return data, len(all_kline) + 20,kline_data_map

    def _clear_input_columns(self, google_sheet, batch) -> None:
        """执行前清空输入列（C5 默认：A列行数<10 跳过；滞空 A~B 列）。"""
        a_num = google_sheet.get_last_row('A')
        if a_num < 10:
            return
        self._log_info(f'{google_sheet.title} 当前A列行数: {a_num},准备滞空 A列 B列')
        google_sheet.clear_range(f"{batch['c5_input_column_a']}2:{batch['c5_input_column_b']}{a_num + 2}")

    def _stamp_combination(self, combination: dict, batch: dict) -> None:
        """组合级打标：写入统一 model_version；C7 覆盖为逐表版本。"""
        if self._model_version:
            combination['model_version'] = self._model_version

    def get_bdl(self, task, name, parameters, config_data):
        """批量执行模板（原 C5/C7 各自复制 198/225 行，C3 批次收敛为基类唯一实现；
        任务差异经 _prepare_batch/_expand_parameters/_clear_input_columns/
        _stamp_combination/_retryable_outer 钩子注入，默认行为 = C5）。"""
        success_count = 0
        failed_count = 0
        try:
            batch = self._prepare_batch(config_data)

            # 仅使用 parameters[0] 作为外层参数列表，真实总组合数为所有 inner combinations 数量之和
            total_combinations = 0
            precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应

            for combinations, column_A_length, kline_data_map in self._expand_all_outer_parameters(batch, parameters):
                precomputed_params.append((combinations, column_A_length, kline_data_map))
                total_combinations += len(combinations)

            # 更新任务总步数
            task.total_steps = total_combinations
            task_result_repository.commit_with_retry()

            # 推送参数组合信息
            self._log_info(f'将执行 {total_combinations} 个参数组合')

            # 检查是否从断点恢复（按组合级别）
            # current_step 表示已完成的组合数；断点恢复必须从下一条开始，
            # 否则每次 watchdog 重启都会重复执行并写入最后一个已完成组合。
            start_index = self._get_resume_start_index(
                task.current_step,
                total_combinations,
            )
            self._log_info(f"任务将从第 {start_index + 1} 个参数组合开始执行")

            # 重置成功/失败计数器；如需精确恢复已完成组合数，可在外部通过历史结果统计
            success_count = start_index

            if batch["kline_source"] != 'custom':
                for google_sheet in self.google_sheets:
                    self._clear_input_columns(google_sheet, batch)

                settle_seconds = self._get_sheet_settle_seconds()
                self._log_info(f'所有表格均滞空，等待{settle_seconds}秒，开始执行后续逻辑')
                if not self._interruptible_sleep(settle_seconds):
                    return success_count, failed_count, 'cancelled'
            else:
                self._log_info('自定义K线模式：保留表格现有K线，仅写入参数')

            processed_index = 0  # 已处理的组合数量
            cache_parameters = {'combination': {}}
            for outer_idx, (combinations, column_A_length, kline_data_map) in enumerate(precomputed_params):
                for combination in combinations:
                    if self._is_cancel_requested():
                        return success_count, failed_count, 'cancelled'
                    # 跳过已完成的组合（断点恢复）
                    if processed_index < start_index:
                        processed_index += 1
                        continue

                    self._stamp_combination(combination, batch)

                    # 原子性检查任务是否被取消（每个外层参数进入前检查一次）
                    def check_task_status():
                        return task_repository.get_status_value(self.task_id)

                    result = safe_db_operation(check_task_status)

                    if not result or result == 'cancelled':
                        self._log_warning("任务已被取消，停止执行")
                        return success_count, failed_count, 'cancelled'

                    current_step = processed_index + 1

                    self._log_step(current_step, total_combinations, "开始执行参数组合")

                    # 推送执行进度
                    progress_msg = f'正在执行第 {current_step}/{total_combinations} 个参数组合'
                    self._log_info(progress_msg)

                    # 执行单个参数组合
                    try:
                        success, result = self._execute_parameter_combination(column_A_length, combination, cache_parameters, config_data, kline_data_map)

                        if success:
                            success_count += 1
                            self._log_info(
                                f'第 {current_step} 个参数组合执行成功，'
                                f'结果摘要: {self._summarize_result_for_log(result)}'
                            )
                        else:
                            self._log_warning(f'第 {current_step} 个参数组合执行失败')
                            failed_count += 1
                            return success_count, failed_count, 'error'

                        cache_parameters['combination'] = combination
                        kline = kline_data_map.get(combination['kline_key'], None)
                        # combination['']
                        combination['kline'] = [kline[0], kline[-1]]

                        self.send_stock_param_result_data(
                            self._build_stock_param_result_payload(
                                name,
                                current_step - 1,
                                combination,
                                result,
                            )
                        )

                        # 更新当前步数为组合级别
                        task.current_step = current_step
                        task_result_repository.commit_with_retry()

                        # 保存结果到数据库
                        stock_name = str(combination.get('stock_name') or '').strip()
                        self._save_task_result(current_step - 1, {
                            **combination,
                            'stock_code': combination['stock_code'],
                            **({'stock_name': stock_name} if stock_name else {}),
                        }, result, success)

                    except SheetCheckError as e:
                        self._record_execution_error_message(e, "execute_parameter_combination")
                        self._log_error(str(e))
                        return success_count, failed_count, 'error'
                    except Exception as e:
                        failed_count += 1
                        # 检查是否是任务被取消
                        try:
                            task_check = task_repository.get_entity(self.task_id)
                            if task_check and task_check.status == 'cancelled':
                                self._log_info(f'第 {current_step} 个参数组合执行中断（任务被取消）: {str(e)}')
                                return success_count, failed_count, 'cancelled'
                        except Exception:  # best-effort 取消探测：失败不中断主流程
                            pass

                        error_summary = self._record_execution_error_message(
                            e,
                            "execute_parameter_combination",
                        )
                        error_msg = f'第 {current_step} 个参数组合执行出错: {error_summary}'
                        self._log_error(error_msg)
                        return success_count, failed_count, 'error'

                    processed_index += 1

            self._log_info(f"批量数据处理完成，总成功: {success_count}, 总失败: {failed_count}")
            return success_count, failed_count, 'completed'

        except Exception as e:
            # 检查是否是任务被取消导致的异常
            try:
                task_check = task_repository.get_entity(self.task_id)
                if task_check and task_check.status == 'cancelled':
                    self._log_info(f'批量数据处理中断（任务被取消）: {str(e)}')
                    return success_count, failed_count, 'cancelled'
            except Exception:  # best-effort 取消探测：失败不中断主流程
                pass

            if self._retryable_outer:
                self._raise_retryable_network_error(e, "批量数据处理网络请求失败")

            error_summary = self._record_execution_error_message(e, "get_bdl")
            self._log_error(f"批量数据处理失败: {error_summary}")
            return 0, 1, 'error'

    @alert_on_failure(
        result_predicate=should_alert_execute_task_result,
        message_builder=build_execute_task_alert,
    )
    def execute_task(self):
        """执行任务的模板方法（C3~C7 统一骨架，C1 收敛为基类唯一实现）。

        子类通过覆盖 get_bdl / _init_google_sheet 钩子体现任务差异；
        取消检查点统一含 stop_event（_is_cancel_requested）与库状态两种信号。
        """
        try:

            # 统一使用应用上下文
            context_app = self.app or current_app
            with context_app.app_context():
                task = task_repository.get_entity(self.task_id)
                self.task = task
                if not task:
                    self._log_error(f'任务 {self.task_id} 不存在')
                    return 'error'

                # 检查任务是否已被取消
                if task.status == TaskStatus.CANCELLED.value:
                    self._log_info(f'任务 {self.task_id} 已被取消，停止执行')
                    return 'cancelled'
                if self._is_cancel_requested():
                    self._log_info(f'task {self.task_id} cancellation requested')
                    return 'cancelled'

                # 解析配置
                if isinstance(task.config, str):
                    try:
                        config_data = loads(task.config)
                    except JSONDecodeError as e:
                        self._log_error(f"配置解析失败: {str(e)}")
                        return 'error'
                else:
                    config_data = task.config or {}

                config_manager = get_config_manager()
                config_data = {**config_manager.get_google_sheet_config(), **config_data}

                # 推送任务开始日志
                self._log_info('开始执行Google Sheet任务')

                # 初始化Google Sheet连接
                self._init_google_sheet(config_data)

                # 获取参数列表
                parameters = config_data.get('parameters', [])
                if not parameters:
                    self._log_error("没有参数配置")
                    return 'error'

                name = task.name
                self.task_name = name
                # 检查任务是否已被取消
                if task.status == TaskStatus.CANCELLED.value:
                    self._log_info(f'任务 {self.task_id} 已被取消，停止执行')
                    return 'cancelled'
                if self._is_cancel_requested():
                    self._log_info(f'task {self.task_id} cancellation requested')
                    return 'cancelled'

                # 历史上的 get_single_stock_template_param 单股参数流已废弃（stock_param 恒为 None），
                # 仅保留默认参数模式路径；对应 final_status 死分支一并移除。
                self._log_info("开始执行参数批量处理（默认参数模式）")
                success_count, failed_count, task_status = self.get_bdl(task, name, parameters, config_data)

                # 根据任务状态决定返回结果
                if task_status == 'cancelled':
                    # 任务被取消，保持cancelled状态
                    self._log_info(f'任务已取消，成功执行: {success_count}, 失败: {failed_count}')
                    return 'cancelled'
                elif task_status == 'error':
                    return 'error'

                if success_count == 0 and failed_count == 0:
                    self._log_error('任务执行失败')
                    return 'error'

                # 刷新汇总索引并推送完成通知
                self._refresh_model_summary_index()
                self.task_ok_to_dd(f'任务执行完成！成功: {success_count}, 失败: {failed_count}')
                # 推送任务完成信息
                completion_msg = f'任务执行完成！成功: {success_count}, 失败: {failed_count}'
                self._log_info(completion_msg)

                return 'completed'

        except Exception as e:
            # 检查是否是任务被取消导致的异常
            try:
                task = task_repository.get_entity(self.task_id)
                if task and task.status == TaskStatus.CANCELLED.value:
                    self._log_info(f'任务已被取消: {str(e)}')
                    return 'cancelled'
            except Exception:  # best-effort 取消探测：失败不中断主流程
                pass

            # 其他异常情况
            root, error_summary = summarize_task_exception(
                self.task_id, e, "execute_task", self.app,
                log_warning=self._log_warning,
            )
            error_msg = f"执行Google Sheet任务失败: {self.task_id}, 错误: {str(root)}"
            self._log_error(error_msg)
            self._log_error(f"任务异常摘要: {error_summary}")
            return 'error'
        finally:
            # 兜底：任何返回路径都把剩余缓冲日志落库（含取消/异常路径）
            self._flush_log_buffer()

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool, return_date=None):
        """保存任务结果到数据库，包含重试逻辑。

        return_date 不为 None 时作为收益序列唯一行来源（空列表即不写序列）；
        为 None 时从 result 提取（C3~C7 行为）。
        """
        def save_result_operation():
            safe_parameters = self._normalize_result_parameters(parameters)
            safe_result = sanitize_json_value(
                self._prepare_result_for_persistence(
                    self._build_task_result_persistence_payload(safe_parameters, result, return_date)
                )
            )
            return_rows = return_date if return_date is not None else extract_return_rows(result)
            series_fields = None
            if return_rows:
                series_fields = build_return_series_fields(
                    return_rows,
                    stock_code=safe_parameters.get("stock_code"),
                    stock_name=self._get_return_series_stock_name(safe_parameters),
                    market_type=self._get_return_series_market_type(safe_parameters),
                    exchange_market=self._get_return_series_exchange_market(safe_parameters),
                )
                if return_date and not series_fields:
                    raise ValueError("收益序列缺少有效日期")
            result_fields = {
                "task_id": self.task_id,
                "step_index": step_index,
                # NaN/Inf 守卫：结果落库遇 NaN 抛 ValueError，禁止静默写 null。
                "parameters": json.dumps(safe_parameters, allow_nan=False),
                "result": json.dumps(safe_result, allow_nan=False),
                "success": success,
            }
            return_fields = {"task_id": self.task_id, **series_fields} if series_fields else None
            task_result_repository.create_with_return(
                result_fields,
                return_fields,
                kline_series_id=safe_parameters.get("kline_series_id"),
            )

        try:
            if self.app:
                # 在后台线程中使用传递的应用实例
                with self.app.app_context():
                    safe_db_operation(save_result_operation)
            else:
                # 在主线程中使用当前应用上下文
                with current_app.app_context():
                    safe_db_operation(save_result_operation)
        except Exception as e:
            task_result_repository.rollback()
            error_msg = f"保存任务结果失败: {str(e)}"
            self._log_error(error_msg)
            raise
            # 注意：这里不能使用_push_log，因为可能导致循环调用

    def _log_info(self, message: str, log_type: str = 'general', **kwargs):
        self._log('info', message, log_type, **kwargs)

    def _log_warning(self, message: str, log_type: str = 'general', **kwargs):
        self._log('warning', message, log_type, **kwargs)

    def _log_error(self, message: str, log_type: str = 'general', **kwargs):
        self._log('error', message, log_type, **kwargs)

    def _record_execution_error_message(
        self,
        exc: Exception,
        phase: str = "google_sheet_service",
    ) -> str:
        try:
            record = record_task_exception(
                self.task_id,
                exc,
                phase,
                self.app,
            )
            return format_task_error_message(record)
        except Exception as update_error:
            logger.warning("记录 Google Sheet 任务错误摘要失败: %s", update_error)
            return f"{exc.__class__.__name__}: {exc}"

    def _log_step(self, step: int, total: int, message: str):
        self._log('info', message, 'step', step=step, total=total)

    def _log_api_error(self, action: str, error: str):
        self._log('error', '', 'api_error', action=action, error=error)

    def _refresh_model_summary_index(self):
        try:
            from app.services.model_summary_service import model_summary_service

            summary = model_summary_service.upsert_task(self.task_id)
            self._log_info(
                f"更新汇总索引完成：处理 {summary.get('processed', 0)} 条结果，"
                f"候选 {summary.get('candidate_records', 0)} 条"
            )
        except Exception as err:
            self._log_warning(f"更新汇总索引失败: {err}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def send_stock_param_result_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.api_client.add_or_modify_stock_param_result(payload) or {}
            return result
        except Exception as err:
            self._log_api_error("发送StockParamResult数据", str(err))
            raise

    def _build_stock_param_result_base_payload(
        self,
        task_name: str,
        task_index: int,
        config_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        stock_code = str(task_name or "").strip()

        return {
            "task_id": self.task_id,
            "stock_code": stock_code,
            "multiplier": 0,
            "danbian": 0,
            "xiancang": 0,
            "zhishu": 0,
            "smoothing": 0,
            "bordering": 0,
            "ml": str(config_data.get("ml") or ""),
            "task_index": task_index,
            "kline_range": dumps(config_data.get("kline",[]),ensure_ascii=False),
            "return_rate": 0,
            "annualized_rate": 0,
            "maxdd": 0,
            "index_rate": 0,
            "index_annualized_rate": 0,
            "max_index_dd": 0,
            "fee_total": 0,
            "fee_annualized": 0,
            "year_rate": 0,
            "turnover_rate": 0,
            "return_beats": 0,
            "dd_beats": 0,
            "max_1y_beats": 0,
            "min_1y_beats": 0,
            "max_theoretical_leverage": 0,
            "avg_theoretical_leverage": 0,
            "unit_theoretical_leverage_return": 0,
            "max_actual_leverage": 0,
            "avg_actual_leverage": 0,
            "unit_actual_leverage_return": 0,
            "start_monthly_std_dev": 0,
            "index_monthly_std_dev": 0,
            "index_annualized_return": 0,
            "start_annualized_return": 0,
            "index_profit_annual": 0,
            "start_profit_annual": 0,
            "index_profit_monthly_percentage": 0,
            "start_profit_monthly_percentage": 0,
            "index_avg_monthly_return_common": 0,
            "start_avg_monthly_return_common": 0,
            "index_monthly_return_volatility": 0,
            "start_monthly_return_volatility": 0,
            "annualized_return_diff": 0,
            "outperform_year": 0,
            "monthly_excess_return_percentage_last_return": 0,
            "avg_monthly_excess_returns": 0,
            "monthly_excess_volatility": 0,
            "max_drawdown": 0,
            "excess_drawdown_winning_rate": 0,
            "start_drawdown": 0,
            "start_maximum_number_of_backtest_repair_days": 0,
            "excess_maximum_number_of_backtest_repair_days": 0,
            "index_sharpe_ratio": 0,
            "start_sharpe_ratio": 0,
            "index_kama_ratio": 0,
            "start_kama_ratio": 0,
            "index_sortino_ratio": 0,
            "start_sortino_ratio": 0,
            "excess_sharpe": 0,
            "excess_sortino": 0,
        }

    def _init_google_sheet(self, config_data: Dict[str, Any]):
        """初始化 Google Sheet 连接（唯一形态：config_data['sheets']）。"""
        try:
            self._log_info("开始初始化Google Sheet连接")

            token_file = config_data.get('token_file', 'data/token.json')
            proxy_url = config_data.get('proxy_url')

            sheets = config_data.get('sheets') or []
            if not sheets:
                error_msg = "缺少spreadsheet_id配置"
                self._log_error(error_msg)
                raise ValueError(error_msg)

            self._log_info(f"连接参数 - sheets: {sheets},Token: {token_file}")
            if proxy_url:
                self._log_info(f"使用代理: {proxy_url}")

            connected_sheets = []
            for sheet in sheets:
                spreadsheet_id = sheet.get('spreadsheet_id')
                sheet_name = sheet.get('sheet_name', 'data')
                google_sheet = GoogleSheet(
                    spreadsheet_id,
                    sheet_name,
                    token_file,
                    proxy_url,
                    task_id=self.task_id,
                )
                if not google_sheet.worksheet:
                    raise Exception("请先选择工作表")
                connected_sheets.append(google_sheet)
                self._log_info(f"已连接工作表: {sheet}")

            self.google_sheets = connected_sheets
            # 单表任务（C3/C31 子任务/单品回测）消费单对象引用
            self.google_sheet = connected_sheets[0] if len(connected_sheets) == 1 else None
            self._log_info("Google Sheet连接初始化成功")
        except Exception as err:
            error_msg = f"初始化Google Sheet连接失败: {err}"
            self._log_error(error_msg)
            raise

    @staticmethod
    def get_worksheets(
        spreadsheet_id: str,
        token_file: str = "data/token.json",
        proxy_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取指定电子表格的标题和工作表列表。"""
        try:
            with GoogleSheet(spreadsheet_id, None, token_file, proxy_url) as google_sheet:
                worksheets = google_sheet.get_all_worksheets()
                if not worksheets:
                    raise ValidationError("未找到任何工作表")

                title = google_sheet.sheet.title if google_sheet.sheet else ""
                return {"title": title, "worksheets": worksheets}
        except Exception as err:
            logger.error("获取工作表列表失败: %s", err)
            raise
