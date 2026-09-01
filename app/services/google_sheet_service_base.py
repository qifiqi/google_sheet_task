import json
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from flask import current_app, has_app_context
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models import Task, TaskLog, db
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.db_retry import safe_db_operation
from app.utils.db_stock_api import StockAPIClient
from app.utils.market import infer_market_type, normalize_stock_code
from app.utils.logger import get_logger
from app.services.task.error_handling import format_task_error_message, record_task_exception


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
            task = db.session.get(Task, self.task_id)
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
            db.session.add(log)
            db.session.commit()

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
                db.session.rollback()
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
        #     config_data.get("stock_code",None)
        #     or str(task_name or "").strip()
        #     # or str(task_name or "").split("-", 1)[0].strip()
        #     or ""
        # )
        # if config_data.get("stock_code",None) in (None, ""):
        #     stock_code = str(task_name or "").strip()
        # else:
        #     stock_code = f'{config_data.get("stock_code",None)}-{task_name}'
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
