import json
import math
from datetime import date, datetime
from typing import Any, Dict, Optional

from flask import current_app, has_app_context
from tenacity import retry, stop_after_attempt, wait_exponential

from app.repositories import task_log_repository, task_repository, task_result_repository
from app.models import TaskLog
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.db_retry import safe_db_operation
from app.utils.db_stock_api import StockAPIClient
from app.utils.market import infer_market_type, normalize_stock_code
from app.utils.return_series import build_return_series_fields, extract_return_rows
from app.utils.logger import get_logger
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.task_error_utils import RetryableNetworkTaskError, is_retryable_network_error, unwrap_exception
from app.exceptions.sheet_check_error import SheetCheckError


logger = get_logger(__name__)

DEFAULT_EXECUTION_DELAY_MIN = 20
DEFAULT_EXECUTION_DELAY_MAX = 30


def should_alert_execute_task_result(result):
    return result == 'error'


def build_execute_task_alert(target, func_name, phase, exc, result):
    if exc is not None:
        return f"{func_name} 执行异常: {type(exc).__name__}: {exc}"

    task = getattr(target, 'task', None)
    task_error = getattr(task, 'error', None)
    if task_error:
        return f"{func_name} 返回失败状态: {result}, 错误信息: {task_error}"
    return f"{func_name} 返回失败状态: {result}"


class BaseGoogleSheetService:
    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        self.config = config
        self.task_id = task_id
        self.app = app
        self.stop_event = stop_event
        self.task_name = ''
        self.task = None
        self.task_logger = get_logger(f"{self.__module__}.{task_id}")
        self.api_client = StockAPIClient()

    @classmethod
    def _sanitize_json_value(cls, value: Any):
        """Recursively convert values into strict JSON-safe Python objects."""
        if isinstance(value, dict):
            return {
                key: cls._sanitize_json_value(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [cls._sanitize_json_value(item) for item in value]

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, float):
            return value if math.isfinite(value) else None

        if value is None or isinstance(value, (str, int, bool)):
            return value

        tolist_method = getattr(value, "tolist", None)
        if callable(tolist_method):
            try:
                return cls._sanitize_json_value(tolist_method())
            except Exception:
                pass

        item_method = getattr(value, "item", None)
        if callable(item_method):
            try:
                return cls._sanitize_json_value(item_method())
            except Exception:
                pass

        return value

    def _normalize_result_parameters(self, parameters: Any) -> dict[str, Any]:
        """Ensure persisted result parameters always contain stock_code."""
        safe = self._sanitize_json_value(parameters)
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
                    else json.loads(self.task.config)
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
                    else json.loads(self.task.config)
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
            return bool(task and task.status == 'cancelled')
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

    def _task_display_name(self) -> str:
        return self.task_name or self.task_id

    def _task_detail_url(self) -> str:
        return f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}"

    def error_dd(self, error_msg):
        result = self.app.notifier.send_task_notification(
            self.task_id,
            notify_type="error",
            summary=error_msg,
            detail_url=self._task_detail_url(),
        )
        return result

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
        if log_type == 'progress':
            percentage = kwargs.get('percentage', 0)
            return f"[Progress {percentage:.1f}%] {message}"
        if log_type == 'api':
            action = kwargs.get('action', '')
            details = kwargs.get('details', '')
            base_msg = f"[API] {action}"
            return f"{base_msg} - {details}" if details else base_msg
        if log_type == 'api_error':
            action = kwargs.get('action', '')
            error = kwargs.get('error', '')
            return f"[API_ERROR] {action} - {error}"
        return message

    def _save_to_database(self, level: str, message: str):
        def save_log_operation():
            log = TaskLog(
                task_id=self.task_id,
                level=level,
                message=TaskLog.normalize_message(message),
            )
            task_log_repository.add_entity(log)
            task_result_repository.commit()

        try:
            if has_app_context():
                safe_db_operation(save_log_operation)
            elif self.app:
                with self.app.app_context():
                    safe_db_operation(save_log_operation)
            else:
                with current_app.app_context():
                    safe_db_operation(save_log_operation)
        except Exception:
            # 提交失败后 SQLAlchemy session 会处于 failed state；必须回滚，
            # 否则后续任务结果写入会触发 PendingRollbackError。
            try:
                task_result_repository.rollback()
            except Exception:
                pass
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
        return json.dumps(
            self._sanitize_json_value(summary),
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

    def _deduplicate_parameter_combinations(self, combinations, kline_data_map):
        """按股票、参数和实际K线区间去除重复回测组合。"""
        deduplicated = []
        seen = set()
        for combination in combinations:
            kline = kline_data_map.get(combination.get('Kline_key'))
            if not kline:
                deduplicated.append(combination)
                continue

            kline_signature = (
                kline[0].get('stock_date'),
                kline[-1].get('stock_date'),
                len(kline),
            )
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

    def _prepare_batch(self, config_data: dict) -> dict:
        """从任务配置提取批量执行所需的标量与自定义K线映射（C5 默认实现）。"""
        kline_source = str(config_data.get('kline_source') or 'auto').strip().lower()
        if kline_source not in ('auto', 'custom'):
            raise ValueError("kline_source 仅支持 auto 或 custom")
        custom_kline_map = None
        if kline_source == 'custom':
            c5_input_column_a = config_data.get('c5_input_column_a').upper()
            c5_input_column_b = config_data.get('c5_input_column_b').upper()
            custom_kline = self._get_custom_kline_data(c5_input_column_a, c5_input_column_b)
            custom_kline_map = {'custom': custom_kline}
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
            "data_source": config_data.get("kline_data_source", "dfcf"),
            "custom_kline_map": custom_kline_map,
        }

    def _expand_parameters(self, outer_param, parameters, batch):
        """单外层参数 → (组合列表, A列长度, KLINE_DATA_MAP)；默认走 C5 签名。"""
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
        )

    def _clear_input_columns(self, google_sheet, batch) -> None:
        """执行前清空输入列（C5 默认：A列行数<10 跳过；滞空 A~B 列）。"""
        a_num = google_sheet.get_last_row('A')
        if a_num < 10:
            return
        self._log_info(f'{google_sheet.title} 当前A列行数: {a_num},准备滞空 A列 B列')
        google_sheet.clear_range(f"{batch['c5_input_column_a']}2:{batch['c5_input_column_b']}{a_num + 2}")

    def _stamp_combination(self, combination: dict, batch: dict) -> None:
        """组合级打标钩子；默认无（C7 覆盖以写入 c7_model_version）。"""
        return None

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

            for outer_param in parameters[0]:
                if batch["kline_source"] == 'custom':
                    combinations, column_A_length, KLINE_DATA_MAP = self._get_custom_parameters(
                        outer_param, parameters, batch["custom_kline_map"]
                    )
                else:
                    combinations, column_A_length, KLINE_DATA_MAP = self._expand_parameters(outer_param, parameters, batch)
                precomputed_params.append((combinations, column_A_length, KLINE_DATA_MAP))
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

                self._log_info('所有表格均滞空，等待20秒，开始执行后续逻辑')
                if not self._interruptible_sleep(20):
                    return success_count, failed_count, 'cancelled'
            else:
                self._log_info('自定义K线模式：保留表格现有K线，仅写入参数')

            processed_index = 0  # 已处理的组合数量
            cache_parameters = {'combination': {}}
            for outer_idx, (combinations, column_A_length, KLINE_DATA_MAP) in enumerate(precomputed_params):
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

                    self._log_step(current_step, total_combinations, f"开始执行参数组合")

                    # 推送执行进度
                    progress_msg = f'正在执行第 {current_step}/{total_combinations} 个参数组合'
                    self._log_info(progress_msg)

                    # 执行单个参数组合
                    try:
                        success, result = self._execute_parameter_combination(column_A_length, combination, cache_parameters, config_data, KLINE_DATA_MAP)

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
                        kline = KLINE_DATA_MAP.get(combination['Kline_key'], None)
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

    def execute_task(self):
        """执行任务的模板方法（原 C4/C5/C7 逐字相同的 97 行骨架，C1 收敛为基类唯一实现）。

        子类通过覆盖 get_bdl / _init_google_sheet 钩子体现任务差异；
        C3 因头部取消检查/多重收益收尾差异保留自己的 execute_task 覆盖。
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
                if task.status == 'cancelled':
                    self._log_info(f'任务 {self.task_id} 已被取消，停止执行')
                    return 'cancelled'

                # 解析配置
                if isinstance(task.config, str):
                    try:
                        config_data = json.loads(task.config)
                    except json.JSONDecodeError as e:
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
                if task.status == 'cancelled':
                    self._log_info(f'任务 {self.task_id} 已被取消，停止执行')
                    return 'cancelled'

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
                if task and task.status == 'cancelled':
                    self._log_info(f'任务已被取消: {str(e)}')
                    return 'cancelled'
            except Exception:  # best-effort 取消探测：失败不中断主流程
                pass

            # 其他异常情况
            root = unwrap_exception(e) or e
            try:
                record = record_task_exception(self.task_id, e, "execute_task", self.app)
                error_summary = format_task_error_message(record)
            except Exception as record_error:
                self._log_warning(f"记录任务异常失败: {record_error}")
                error_summary = f"{root.__class__.__name__}: {root}"
            error_msg = f"执行Google Sheet任务失败: {self.task_id}, 错误: {str(root)}"
            self._log_error(error_msg)
            self._log_error(f"任务异常摘要: {error_summary}")
            return 'error'

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool, return_date=None):
        """保存任务结果到数据库，包含重试逻辑。

        return_date 不为 None 时作为收益序列唯一行来源（空列表即不写序列）；
        为 None 时从 result 提取（C3~C7 行为）。
        """
        def save_result_operation():
            safe_parameters = self._normalize_result_parameters(parameters)
            safe_result = self._sanitize_json_value(
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
                "parameters": json.dumps(safe_parameters, allow_nan=False),
                "result": json.dumps(safe_result, allow_nan=False),
                "success": success,
            }
            return_fields = {"task_id": self.task_id, **series_fields} if series_fields else None
            task_result_repository.create_with_return(result_fields, return_fields)

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

    def _log_progress(self, percentage: float, message: str):
        self._log('info', message, 'progress', percentage=percentage)

    def _log_api(self, action: str, details: str = ''):
        self._log('info', '', 'api', action=action, details=details)

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
        # stock_code = (
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
            "kline_range": json.dumps(config_data.get("kline",[]),ensure_ascii=False),
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def get_single_stock_template_param(self, stock_no: str) -> Optional[Dict[str, Any]]:
        """获取单个股票模板参数。"""
        try:
            result = self.api_client.get_single_stock_template_param(stock_no)
            return result
        except Exception as err:
            self._log_api_error("获取股票模板参数", str(err))
            raise

    def _init_google_sheet(self, config_data: Dict[str, Any]):
        """初始化 Google Sheet 连接，兼容单表、多表和嵌套 sheet 配置。"""
        try:
            self._log_info("开始初始化Google Sheet连接")

            token_file = config_data.get('token_file', 'data/token.json')
            proxy_url = config_data.get('proxy_url')

            if 'sheets' in config_data:
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
                self._log_info("Google Sheet连接初始化成功")
                return

            spreadsheet_id = config_data.get('spreadsheet_id')
            sheet_name = config_data.get('sheet_name', 'data')
            if isinstance(config_data.get('sheet'), dict):
                sheet = config_data['sheet']
                spreadsheet_id = sheet.get('spreadsheet_id', spreadsheet_id)
                sheet_name = sheet.get('sheet_name', sheet_name)

            if not spreadsheet_id:
                error_msg = "缺少spreadsheet_id配置"
                self._log_error(error_msg)
                raise ValueError(error_msg)

            self._log_info(
                f"连接参数 - Spreadsheet ID: {spreadsheet_id}, Sheet: {sheet_name}, Token: {token_file}"
            )
            if proxy_url:
                self._log_info(f"使用代理: {proxy_url}")

            self.google_sheet = GoogleSheet(
                spreadsheet_id,
                sheet_name,
                token_file,
                proxy_url,
                task_id=self.task_id,
            )
            if not self.google_sheet.worksheet:
                raise Exception("请先选择工作表")

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
                    raise ValueError("未找到任何工作表")

                title = google_sheet.sheet.title if google_sheet.sheet else ""
                return {"title": title, "worksheets": worksheets}
        except Exception as err:
            logger.error("获取工作表列表失败: %s", err)
            raise
