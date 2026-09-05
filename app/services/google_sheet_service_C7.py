import json
import random
import re
import time
from typing import Dict, Any

from flask import current_app
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.repositories import task_repository, task_result_repository
from app.exceptions.checkForErrors import checkForErrors
from app.models import TaskResult, TaskResultReturn
from app.utils.return_series import build_return_series_fields, extract_return_rows
from app.services.google_sheet_service_base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.services.stock_metadata_service import upsert_stock_metadata_in_session
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value
from app.services.xpl_service import xpl_analyzer
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.logger import get_logger
from app.utils.yf_api import YFApi
from app.utils.task_error_utils import (
    RetryableNetworkTaskError,
    is_retryable_network_error,
    unwrap_exception,
)
from app.utils.kline_validation import require_kline_rows
from app.services.kline_service import KlineService, get_kline_price_field
from app.utils.c7_result_normalizer import normalize_c7_result_metrics


logger = get_logger(__name__)


class GoogleSheetService(BaseGoogleSheetService):
    """Google Sheet服务 - C7"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.google_sheets: list[GoogleSheet] = []
        self.xpl = xpl_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()
        self.kline_service = KlineService(dfcf_api=self.dfcf_api, yahoo_api=self.YF_api)

    def _raise_retryable_network_error(self, exc, context):
        if is_retryable_network_error(exc):
            root = unwrap_exception(exc) or exc
            raise RetryableNetworkTaskError(f"{context}: {root}") from exc

    @staticmethod
    def _get_resume_start_index(current_step: int | None, total_combinations: int) -> int:
        """返回下一条待执行组合的下标。"""
        return min(max(int(current_step or 0), 0), total_combinations)

    @staticmethod
    def _get_c7_model_version(config_data: Dict[str, Any], google_sheet=None) -> str:
        """读取单表 C7 版本，旧任务和缺省配置统一按 C7.0.2 处理。"""
        spreadsheet_id = getattr(google_sheet, "spreadsheet_id", None)
        sheet_title = str(getattr(google_sheet, "title", "") or "").strip().upper()
        for sheet_config in config_data.get("sheets") or []:
            if spreadsheet_id and sheet_config.get("spreadsheet_id") == spreadsheet_id:
                version = str(sheet_config.get("c7_model_version") or "").strip().lower()
                if version in ("c7_0_2", "c7_0_3"):
                    return version
                if "C7.0.3" in sheet_title or "C7_0_3" in sheet_title:
                    return "c7_0_3"
                return "c7_0_2"

        if "C7.0.3" in sheet_title or "C7_0_3" in sheet_title:
            return "c7_0_3"
        version = str(config_data.get("c7_model_version") or "c7_0_2").strip().lower()
        return version if version in ("c7_0_2", "c7_0_3") else "c7_0_2"

    @classmethod
    def _get_c7_layout(cls, config_data: Dict[str, Any], google_sheet=None) -> Dict[str, Any]:
        """根据模型版本构建单表输入和结果布局。"""
        version = cls._get_c7_model_version(config_data, google_sheet)
        parameter_positions = config_data.get("c7_parameter_positions") or ["A1", "B1"]
        check_positions = config_data.get("c7_check_positions") or ["G1", "H1"]

        if version == "c7_0_3":
            return {
                "version": version,
                "start_row": int(config_data.get("c7_0_3_kline_start_row") or 2),
                "date_column": str(config_data.get("c7_0_3_kline_date_column") or "CC").upper(),
                "open_column": str(config_data.get("c7_0_3_kline_open_column") or "CD").upper(),
                "high_column": str(config_data.get("c7_0_3_kline_high_column") or "CE").upper(),
                "low_column": str(config_data.get("c7_0_3_kline_low_column") or "CF").upper(),
                "close_column": str(config_data.get("c7_0_3_kline_close_column") or "CG").upper(),
                "output_range_1": config_data.get("c7_0_3_output_range_1") or config_data.get("c5_output_range_1") or "D2:D20",
                "output_range_2": config_data.get("c7_0_3_output_range_2") or config_data.get("c5_output_range_2") or "D22:F25",
                "output_column_j": config_data.get("c7_0_3_output_column_j") or config_data.get("c5_output_column_j") or "J",
                "output_column_l": config_data.get("c7_0_3_output_column_l") or config_data.get("c5_output_column_l") or "L",
                "parameter_positions": parameter_positions,
                "check_positions": check_positions,
            }

        return {
            "version": "c7_0_2",
            "start_row": 2,
            "date_column": str(config_data.get("c7_input_column_a") or "A").upper(),
            "value_column": str(config_data.get("c7_input_column_b") or "B").upper(),
            "output_range_1": config_data.get("c7_output_range_1") or "D8:D26",
            "output_range_2": config_data.get("c7_output_range_2") or "D28:F31",
            "output_column_j": config_data.get("c7_output_column_j") or "J",
            "output_column_l": config_data.get("c7_output_column_l") or "L",
            "parameter_positions": parameter_positions,
            "check_positions": check_positions,
        }

    @staticmethod
    def _get_c7_write_end_column(layout: Dict[str, Any]) -> str:
        return layout.get("close_column") or layout.get("value_column") or layout["date_column"]

    def _expand_random_price_groups(self, combinations, kline_data_map, price_mode, random_price_range, random_group_count):
        if price_mode != "random_price":
            return combinations, kline_data_map
        grouped_data = []
        grouped_map = {}
        for combination in combinations:
            source_key = combination["Kline_key"]
            source_kline = kline_data_map[source_key]
            for random_group in range(1, int(random_group_count or 1) + 1):
                group_key = f"{source_key}:random-{random_group}"
                if group_key not in grouped_map:
                    random_generator = random.Random(
                        f"{self.task_id}:{combination.get('stock_code', '')}:"
                        f"{source_key}:{random_price_range}:{random_group}"
                    )
                    grouped_map[group_key] = KlineService.build_price_rows(
                        source_kline,
                        price_mode,
                        include_ohlc=True,
                        random_price_range=random_price_range,
                        random_generator=random_generator,
                    )
                item = dict(combination)
                item["Kline_key"] = group_key
                item["year"] = group_key
                item["random_group"] = random_group
                grouped_data.append(item)
        return grouped_data, grouped_map

    @staticmethod
    def _get_c7_input_last_row(google_sheet, layout: Dict[str, Any]) -> int:
        if layout["version"] != "c7_0_3":
            return google_sheet.get_last_row(layout["date_column"])
        columns = [
            layout["date_column"],
            layout["open_column"],
            layout["high_column"],
            layout["low_column"],
            layout["close_column"],
        ]
        rows = [google_sheet.get_last_row(column) for column in dict.fromkeys(columns)]
        return max((row for row in rows if row >= 0), default=0)

    @staticmethod
    def _get_c7_range_start(range_a1: str) -> tuple[str, int]:
        match = re.match(r"^([A-Z]+)(\d+)", str(range_a1 or "").upper())
        if not match:
            raise ValueError(f"无效的 C7 结果范围: {range_a1}")
        return match.group(1), int(match.group(2))

    @staticmethod
    def _validate_c7_ohlc_rows(rows):
        for index, row in enumerate(rows, start=1):
            for field in ("open", "high", "low", "close"):
                if row.get(field) in (None, ""):
                    raise ValueError(f"C7.0.3 K线第 {index} 条缺少 OHLC 字段 {field}")

    @staticmethod
    def _calculate_c7_0_3_index_returns(kline_rows):
        """以 C7.0.3 OHLC 收盘价计算相对首日的累计指数收益。"""
        base_close = None
        index_returns = []

        for index, row in enumerate(kline_rows, start=1):
            try:
                close_price = float(row["close"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"C7.0.3 K线第 {index} 条收盘价无效") from error
            if close_price <= 0:
                raise ValueError(f"C7.0.3 K线第 {index} 条收盘价必须大于 0")

            if base_close is None:
                base_close = close_price
            index_returns.append(close_price / base_close - 1)

        return index_returns

    @staticmethod
    def _to_decimal_ratio(value: Any) -> float:
        """Convert percentage-like values into decimal ratios for outbound payloads."""
        if value in (None, ""):
            return 0

        raw_value = value
        if isinstance(value, str):
            raw_value = value.strip().replace("%", "").replace(",", "")
            if raw_value == "":
                return 0

        try:
            return float(raw_value) / 100
        except (TypeError, ValueError):
            return 0

    @alert_on_failure(
        result_predicate=should_alert_execute_task_result,
        message_builder=build_execute_task_alert,
    )
    def execute_task(self):
        """执行Google Sheet任务"""
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
                    # # 推送任务取消通知
                    # self.task_ok_to_dd(f'任务已取消！成功执行: {success_count}, 失败: {failed_count}')
                    return 'cancelled'
                elif task_status == 'error':
                    return 'error'

                if success_count == 0 and failed_count == 0:
                    self._log_error('任务执行失败')
                    return 'error'

                # 推送任务完成通知
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
            except:
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



    def _build_stock_param_result_payload(
        self,
        task_name: str,
        task_index: int,
        combination: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = self._build_stock_param_result_base_payload(
            task_name,
            task_index,
            {
                "stock_code": combination.get("stock_code"),
                "ml": combination.get("B1"),
                "kline_range": json.dumps(combination['kline']),
            },
        )
        first_value = next(iter(result.values()), None) if isinstance(result, dict) else None
        if isinstance(first_value, dict):
            result = first_value
        model_version = combination.get("c7_model_version", "c7_0_2")
        if model_version != "c7_0_3":
            result = normalize_c7_result_metrics(result)
        analyze_result = result.get('flat_result') if isinstance(result.get('flat_result'), dict) else result

        def metric_value(c5_cell: str) -> Any:
            """C7.0.2 使用偏移结果区，C7.0.3 与 C5 使用同一结果区。"""
            row_offset = 0 if model_version == "c7_0_3" else 6
            return result.get(f"D{int(c5_cell[1:]) + row_offset}", 0)

        payload.update({
            "multiplier": combination.get("A1", 0),
            "ml": combination.get("B1"),
            "return_rate": self._to_decimal_ratio(metric_value("D2")),
            "annualized_rate": self._to_decimal_ratio(metric_value("D3")),
            "maxdd": self._to_decimal_ratio(metric_value("D4")),
            "index_rate": self._to_decimal_ratio(metric_value("D5")),
            "index_annualized_rate": self._to_decimal_ratio(metric_value("D6")),
            "max_index_dd": self._to_decimal_ratio(metric_value("D7")),
            "fee_total": self._to_decimal_ratio(metric_value("D8")),
            "fee_annualized": self._to_decimal_ratio(metric_value("D9")),
            "turnover_rate": metric_value("D10"),
            "return_beats": self._to_decimal_ratio(metric_value("D11")),
            "dd_beats": self._to_decimal_ratio(metric_value("D12")),
            "max_1y_beats": self._to_decimal_ratio(metric_value("D13")),
            "min_1y_beats": self._to_decimal_ratio(metric_value("D14")),
            "max_theoretical_leverage": metric_value("D15"),
            "avg_theoretical_leverage": metric_value("D16"),
            "unit_theoretical_leverage_return": self._to_decimal_ratio(metric_value("D17")),
            "max_actual_leverage": metric_value("D18"),
            "avg_actual_leverage": metric_value("D19"),
            "unit_actual_leverage_return": self._to_decimal_ratio(metric_value("D20")),
            "start_monthly_std_dev": analyze_result.get("start_monthly_std_dev", 0),
            "index_monthly_std_dev": analyze_result.get("index_monthly_std_dev", 0),
            "index_annualized_return": analyze_result.get("index_annualized_return", 0),
            "start_annualized_return": analyze_result.get("start_annualized_return", 0),
            "index_profit_annual": analyze_result.get("index_profit_annual", 0),
            "start_profit_annual": analyze_result.get("start_profit_annual", 0),
            "index_profit_monthly_percentage": analyze_result.get("index_profit_monthly_percentage", 0),
            "start_profit_monthly_percentage": analyze_result.get("start_profit_monthly_percentage", 0),
            "index_avg_monthly_return_common": analyze_result.get("index_avg_monthly_return_common", 0),
            "start_avg_monthly_return_common": analyze_result.get("start_avg_monthly_return_common", 0),
            "index_monthly_return_volatility": analyze_result.get("index_monthly_return_volatility", 0),
            "start_monthly_return_volatility": analyze_result.get("start_monthly_return_volatility", 0),
            "annualized_return_diff": analyze_result.get("annualized_return_diff", 0),
            "outperform_year": analyze_result.get("outperform_year", 0),
            "monthly_excess_return_percentage_last_return": analyze_result.get(
                "monthly_excess_return_percentage_last_return",
                0,
            ),
            "avg_monthly_excess_returns": analyze_result.get("avg_monthly_excess_returns", 0),
            "monthly_excess_volatility": analyze_result.get("monthly_excess_volatility", 0),
            "max_drawdown": analyze_result.get("max_drawdown", 0),
            "excess_drawdown_winning_rate": analyze_result.get("excess_drawdown_winning_rate", 0),
            "start_drawdown": analyze_result.get("start_drawdown", 0),
            "start_maximum_number_of_backtest_repair_days": analyze_result.get(
                "start_maximum_number_of_backtest_repair_days",
                0,
            ),
            "excess_maximum_number_of_backtest_repair_days": analyze_result.get(
                "excess_maximum_number_of_backtest_repair_days",
                0,
            ),
            "index_sharpe_ratio": analyze_result.get("index_sharpe_ratio", 0),
            "start_sharpe_ratio": analyze_result.get("start_sharpe_ratio", 0),
            "index_kama_ratio": analyze_result.get("index_kama_ratio", 0),
            "start_kama_ratio": analyze_result.get("start_kama_ratio", 0),
            "index_sortino_ratio": analyze_result.get("index_sortino_ratio", 0),
            "start_sortino_ratio": analyze_result.get("start_sortino_ratio", 0),
            "excess_sharpe": analyze_result.get("excess_sharpe", 0),
            "excess_sortino": analyze_result.get("excess_sortino", 0),
        })
        return payload

    def get_bdl(self, task, name, parameters, config_data):
        """执行批量数据处理"""
        success_count = 0
        failed_count = 0
        try:
            # 计算总参数组合数（按每个具体组合计数）
            kline_source = str(config_data.get('kline_source') or 'auto').strip().lower()
            if kline_source not in ('auto', 'custom'):
                raise ValueError("kline_source 仅支持 auto 或 custom")
            count_mode = config_data.get('count_mode', 'n_plus_1')
            price_mode = config_data.get('price_mode', 'vwap_price')
            random_price_range = config_data.get('random_price_range', 'high_low')
            random_group_count = int(config_data.get('random_group_count') or 1)
            date_range_mode = config_data.get('date_range_mode',[])
            exclude_recent_years = config_data.get(
                'exclude_recent_years',
                config_data.get('exclude_years', [])
            )
            end_date = config_data.get('end_date')
            start_date = config_data.get('start_date')
            market_type = config_data.get('market_type')
            adjust_type = config_data.get('kline_adjustment')
            custom_kline_map = None
            if kline_source == 'custom':
                first_layout = self._get_c7_layout(config_data, self.google_sheets[0])
                if first_layout["version"] == "c7_0_3":
                    custom_kline = self._get_custom_kline_data(
                        first_layout["date_column"],
                        first_layout["close_column"],
                        start_row=first_layout["start_row"],
                        ohlc_columns=first_layout,
                    )
                else:
                    custom_kline = self._get_custom_kline_data(
                        first_layout["date_column"],
                        first_layout["value_column"],
                        start_row=first_layout["start_row"],
                    )
                custom_kline_map = {'custom': custom_kline}

            # 仅使用 parameters[0] 作为外层参数列表，真实总组合数为所有 inner combinations 数量之和
            total_combinations = 0
            precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应

            for outer_param in parameters[0]:
                if kline_source == 'custom':
                    combinations, column_A_length,KLINE_DATA_MAP = self._get_custom_parameters(
                        outer_param, parameters, custom_kline_map
                    )
                else:
                    combinations, column_A_length,KLINE_DATA_MAP = self._get_all_parameters(
                        outer_param, count_mode, price_mode, end_date, start_date, market_type,
                        date_range_mode, exclude_recent_years, parameters, adjust_type,
                        random_price_range=random_price_range, random_group_count=random_group_count,
                        data_source=config_data.get("kline_data_source", "dfcf")
                    )
                precomputed_params.append((combinations, column_A_length,KLINE_DATA_MAP))
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

            if kline_source != 'custom':
                for google_sheet in self.google_sheets:
                    layout = self._get_c7_layout(config_data, google_sheet)
                    last_row = self._get_c7_input_last_row(google_sheet, layout)
                    if last_row < layout["start_row"]:
                        continue
                    end_column = self._get_c7_write_end_column(layout)
                    self._log_info(
                        f'{google_sheet.title} 当前K线行数: {last_row},准备清空 '
                        f'{layout["date_column"]}{layout["start_row"]}:{end_column}{last_row}'
                    )
                    google_sheet.clear_range(
                        f'{layout["date_column"]}{layout["start_row"]}:{end_column}{last_row}'
                    )

                self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
                if not self._interruptible_sleep(20):
                    return success_count, failed_count, 'cancelled'
            else:
                self._log_info('自定义K线模式：保留表格现有K线，仅写入参数')

            processed_index = 0  # 已处理的组合数量
            cache_parameters = {'combination': {}}
            for outer_idx, (combinations, column_A_length,KLINE_DATA_MAP) in enumerate(precomputed_params):
                for combination in combinations:
                    if self._is_cancel_requested():
                        return success_count, failed_count, 'cancelled'
                    # 跳过已完成的组合（断点恢复）
                    if processed_index < start_index:
                        processed_index += 1
                        continue

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
                        success, result = self._execute_parameter_combination(column_A_length, combination,cache_parameters, config_data,KLINE_DATA_MAP)

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
                        combination['kline'] = [kline[0],kline[-1]]
                        combination['c7_model_version'] = self._get_c7_model_version(
                            config_data,
                            self.google_sheets[0],
                        )

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
                            'stock_code':combination['stock_code'],
                            **({'stock_name': stock_name} if stock_name else {}),
                        }, result, success)


                    except checkForErrors as e:
                        self._log_error(str(e))
                        task.error = e
                        return success_count, failed_count, 'error'
                    except Exception as e:
                        failed_count += 1
                        # 检查是否是任务被取消
                        task.error = e
                        try:
                            task_check = task_repository.get_entity(self.task_id)
                            if task_check and task_check.status == 'cancelled':
                                self._log_info(f'第 {current_step} 个参数组合执行中断（任务被取消）: {str(e)}')
                                return success_count, failed_count, 'cancelled'
                        except:
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
            self._raise_retryable_network_error(e, "批量数据处理网络请求失败")
            # 检查是否是任务被取消导致的异常
            task.error = e
            try:
                task_check = task_repository.get_entity(self.task_id)
                if task_check and task_check.status == 'cancelled':
                    self._log_info(f'批量数据处理中断（任务被取消）: {str(e)}')
                    return success_count, failed_count, 'cancelled'
            except:
                pass

            error_summary = self._record_execution_error_message(e, "get_bdl")
            self._log_error(f"批量数据处理失败: {error_summary}")
            return 0, 1, 'error'

    @retry(
        stop=stop_after_attempt(3),  # 最多尝试3次
        wait=wait_exponential(multiplier=1, min=4, max=10),  # 指数退避：4s, 6s, 10s...
        reraise=True,  # 重试耗尽后重新抛出原始异常
        retry=retry_if_result(lambda result: result[0] is False)
    )
    # @validate_result_dict(
    #     none_values=(None, '', ' ', '#N/A', '#DIV/0!', '#ERROR!', '#VALUE!', '#REF!', '#NAME?', '#NUM!'))
    def _execute_parameter_combination(self, column_A_length, combination,cache_parameters, config_data: Dict[str, Any],KLINE_DATA_MAP) -> tuple[
        bool, Dict[str, Any]]:
        """执行单个参数组合"""
        try:
            initial_results = {}
            results = {}
            sheet_layouts = {
                google_sheet.spreadsheet_id: self._get_c7_layout(config_data, google_sheet)
                for google_sheet in self.google_sheets
            }
            parameter_positions = next(iter(sheet_layouts.values()))["parameter_positions"]
            c7_parameter_1 = f"xm:{combination[parameter_positions[0]]}"
            c7_parameter_2 = f"ml:{combination[parameter_positions[1]]}"
            base_cell_updates = {
                parameter_positions[0]: c7_parameter_1,
                parameter_positions[1]: c7_parameter_2,
            }
            Kline_key = combination['Kline_key']
            is_custom_kline = str(config_data.get('kline_source') or 'auto').strip().lower() == 'custom'
            current_kline = require_kline_rows(
                combination.get('stock_code', ''),
                config_data.get('market_type', ''),
                KLINE_DATA_MAP.get(Kline_key),
                context=f"K线区间 {Kline_key}",
            )
            if any(layout["version"] == "c7_0_3" for layout in sheet_layouts.values()):
                self._validate_c7_ohlc_rows(current_kline)

            def set_googl_val(initial_result_sleep=None):
                _combination = cache_parameters['combination']
                cache_Kline_key = _combination.get('Kline_key',"")
                cache_stock_code = str(_combination.get('stock_code') or '').strip()
                current_stock_code = str(combination.get('stock_code') or '').strip()
                kline = current_kline
                _kline_len = len(kline)
                kline_changed = (
                    Kline_key != cache_Kline_key
                    or current_stock_code != cache_stock_code
                    or initial_result_sleep is not None
                )

                if is_custom_kline:
                    self._log_info(f"自定义K线模式，不修改K线列，只写入参数 combination:{combination}")
                elif kline_changed:
                    for google_sheet in self.google_sheets:
                        layout = sheet_layouts[google_sheet.spreadsheet_id]
                        last_row = self._get_c7_input_last_row(google_sheet, layout)
                        end_row = max(last_row, layout["start_row"] + column_A_length)
                        end_column = self._get_c7_write_end_column(layout)
                        google_sheet.clear_range(
                            f'{layout["date_column"]}{layout["start_row"]}:{end_column}{end_row}'
                        )

                else:
                    self._log_info(f"同源数据，不需要修改k线，改动参数就行 combination:{combination},cache_parameters:{cache_parameters}")

                if initial_result_sleep:
                    self._log_info(f"刷新参数等待：{initial_result_sleep}秒")
                    if not self._interruptible_sleep(initial_result_sleep):
                        raise RuntimeError("task cancelled")

                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(
                        layout["output_range_1"],
                        # value_render_option="UNFORMATTED_VALUE",
                    )

                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    cell_updates = dict(base_cell_updates)
                    if not is_custom_kline and kline_changed:
                        for index, item in enumerate(kline):
                            cell_num = layout["start_row"] + index
                            cell_updates[f'{layout["date_column"]}{cell_num}'] = item.get("stock_date", "")
                            if layout["version"] == "c7_0_3":
                                cell_updates[f'{layout["open_column"]}{cell_num}'] = item.get("open", "")
                                cell_updates[f'{layout["high_column"]}{cell_num}'] = item.get("high", "")
                                cell_updates[f'{layout["low_column"]}{cell_num}'] = item.get("low", "")
                                cell_updates[f'{layout["close_column"]}{cell_num}'] = item.get("close", "")
                            else:
                                cell_updates[f'{layout["value_column"]}{cell_num}'] = item.get("stock_val", "")
                    self._log_info(f"向Google Sheet写入参数: {google_sheet.title} 长度：{len(cell_updates)}")
                    google_sheet.update_jumped_cells(cell_updates)

            set_googl_val()
            kline = current_kline

            def check_result(check_values):
                _check_values = {}
                for _position, _value in check_values.items():
                    if _value is None or (isinstance(_value, str) and not _value.strip()) or not is_valid_result_value(_value):
                        self._log_info(f"结果位置 {_position} 值为空或无效，跳过重新检查：{_value}")
                        raise Exception(f"结果位置 {_position} 值为空或无效，跳过重新检查：{_value}")

                    if str(_value).strip().startswith(("#", "#N/A")):
                        _error_msg = f"获取结果位置 {_position} 时出错: {str(_value)}"
                        raise checkForErrors(f"检查报错，出现#|#N/A 这种异常错误，联系用户检查 {_error_msg}")

                    if isinstance(_value, str) and '%' in _value:
                        _value = float(_value.replace('%', '').replace(',', '')) / 100
                    if isinstance(_value, str) and ',' in _value:
                        _value = float(_value.replace(',', ''))
                    if _value == '-':
                        continue
                    _check_values[_position] = _value
                return _check_values

            def _validate_check_values(check_values: Dict[str, Any], spreadsheet_id, layout: Dict[str, Any]) -> bool:
                """验证检查位置的值是否有效"""
                if not check_values:
                    return False

                check_positions = layout["check_positions"]
                output_range_1 = layout["output_range_1"]
                check_positions_c_v = check_values.get(":".join(check_positions)) or {}
                output_range_1_c_v = check_values.get(output_range_1) or {}
                # for position, value in check_values.items():
                #     if not value or value in ['#DIV/0!', '', '#N/A', '#ERROR!', '#VALUE!']:
                #         return False
                #     if 'target' in str(value).lower():
                #         return False

                _check_values = initial_results[spreadsheet_id]
                if layout["version"] != "c7_0_3":
                    if (c7_parameter_1 != check_positions_c_v.get(check_positions[0])
                            and c7_parameter_2 != check_positions_c_v.get(check_positions[1])):
                        self._log_info(
                            f"c7_parameter_1:{c7_parameter_1} != {check_positions[0]}"
                            f"{str(check_positions_c_v.get(check_positions[0]) or '').strip()} "
                            f"c7_parameter_2:{c7_parameter_2} != {check_positions[1]}"
                            f"{str(check_positions_c_v.get(check_positions[1]) or '').strip()}"
                        )
                        # 校验参数是否成功响应
                        return False

                output_column, output_row = self._get_c7_range_start(output_range_1)
                first_output_cell = f"{output_column}{output_row}"
                second_output_cell = f"{output_column}{output_row + 1}"
                if (_check_values.get(first_output_cell) == output_range_1_c_v.get(first_output_cell)
                        and _check_values.get(second_output_cell) == output_range_1_c_v.get(second_output_cell)):
                    # 校验收益和年化是否ok
                    return False

                return True

            first_kline = kline[0] if kline else {}
            last_kline = kline[-1] if kline else {}
            self._log_info(
                "开始轮询结果："
                f"股票代码={combination.get('stock_code', '')}，"
                f"股票名称={combination.get('stock_name', '')}，"
                f"参数A1={combination.get('A1', '')}，"
                f"参数B1={combination.get('B1', '')}，"
                f"Kline_key={Kline_key}，"
                f"K线行数={len(kline)}，"
                f"日期范围={first_kline.get('stock_date', '')}~{last_kline.get('stock_date', '')}，"
                f"首条K线={first_kline}，末条K线={last_kline}"
            )

            # 定时检查是否完成（最多检查60次，20-30秒）
            delay_min, delay_max = self._get_execution_poll_delay_bounds()
            for attempt in range(60):

                # 定期刷新参数，防止模型卡顿
                if attempt != 0 and (attempt % 10 == 0 or attempt in [5,15,25,35]):
                    self._log_info(f"刷新参数")
                    set_googl_val(20)

                _ = self._get_execution_poll_delay(attempt, delay_min, delay_max)
                self._log_info(f"第 {attempt + 1} 次检查执行状态... delay {_} 秒")
                if not self._interruptible_sleep(_):
                    raise RuntimeError("task cancelled")
                all_num = 0
                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    output_range_1 = layout["output_range_1"]
                    output_range_2 = layout["output_range_2"]
                    output_column_j = layout["output_column_j"]
                    output_column_l = layout["output_column_l"]
                    check_positions = layout["check_positions"]
                    _result = {}
                    batch_results = google_sheet.get_ranges(
                       [output_range_1, ":".join(check_positions)]
                        # value_render_option="UNFORMATTED_VALUE",
                    )

                    if _validate_check_values(batch_results, google_sheet.spreadsheet_id, layout):
                        _result.update(batch_results.get(output_range_1, {}))
                        _result['result_parameters'] = batch_results.get(":".join(check_positions))

                        # # _result = check_result(_result)
                        # _result_yearly = google_sheet.get_range(c7_output_range_2)
                        # # _result_yearly = check_result(google_sheet.get_range(c7_output_range_2))
                        # _result.update(_result_yearly)
                        #
                        # try:
                        #     _index_return = check_result(
                        #         google_sheet.get_range(f"{c7_output_column_j}2:{c7_output_column_j}{len(kline) + 1}")
                        #     )
                        #     _start_return = check_result(
                        #         google_sheet.get_range(f"{c7_output_column_l}2:{c7_output_column_l}{len(kline) + 1}")
                        #     )
                        # except Exception as e:
                        #     self._log_info(f"获取结果位置 {c7_output_column_j}2:{c7_output_column_j}{len(kline) + 1} 时出错：{str(e)}")
                        #     self._log_info(f"_result：{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                        #     break
                        # _result = check_result(_result)
                        if layout["version"] == "c7_0_3":
                            merged_return_range_a1 = (
                                f"{output_column_l}2:{output_column_l}{len(kline) + 1}"
                            )
                        else:
                            merged_return_range_a1 = f"{output_column_j}2:{output_column_l}{len(kline) + 1}"
                        batch_range_values = google_sheet.get_ranges([
                            output_range_2,
                            merged_return_range_a1,
                        ])
                        _result_yearly = batch_range_values.get(output_range_2, {})
                        # _result_yearly = check_result(google_sheet.get_range(c7_output_range_2))
                        _result.update(_result_yearly)

                        try:
                            merged_return_range = batch_range_values.get(merged_return_range_a1, {})
                            if layout["version"] == "c7_0_3":
                                first_return_position = f"{output_column_l}2"
                                if str(merged_return_range.get(first_return_position, "")).strip() == "#DIV/0!":
                                    merged_return_range[first_return_position] = 0
                            _start_return = check_result({
                                position: value
                                for position, value in merged_return_range.items()
                                if position.startswith(output_column_l)
                            })
                            if layout["version"] == "c7_0_3":
                                _index_returns = self._calculate_c7_0_3_index_returns(kline)
                            else:
                                _index_return = check_result({
                                    position: value
                                    for position, value in merged_return_range.items()
                                    if position.startswith(output_column_j)
                                })
                        except Exception as e:
                            self._log_info(f"获取结果位置 {merged_return_range_a1} 时出错：{str(e)}")
                            self._log_info(f"_result：{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                            break

                        _index_return_date = []
                        _start_return_date = []
                        _return_data = []
                        _index_start_return_date = []
                        for i in range(len(kline)):
                            # _index_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _index_return[f"{c7_output_column_j}{i + 2}"]
                            # })
                            # _start_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _start_return[f"{c7_output_column_l}{i + 2}"]
                            # })
                            _return_data.append({
                                'date': kline[i].get('stock_date'),
                                'index_return': (
                                    _index_returns[i]
                                    if layout["version"] == "c7_0_3"
                                    else _index_return[f"{output_column_j}{i + 2}"]
                                ),
                                'start_return': _start_return[f"{output_column_l}{i + 2}"]
                            })

                        # _index_return_xpl = self.xpl.get_xpl(_index_return_date,'stock_date','stock_val')
                        # _start_return_xpl = self.xpl.get_xpl(_start_return_date,'stock_date','stock_val')
                        flat_result, metrics_payload = self.xpl.get_return_analysis_v1(_return_data)
                        # _result['index_return_xpl'] = _index_return_xpl
                        # _result['start_return_xpl'] = _start_return_xpl
                        _result['metrics_payload'] = metrics_payload
                        _result[f"flat_result"] = flat_result
                        _result['_return_date'] = _return_data

                        results[f"{google_sheet.spreadsheet_id}__{google_sheet.title}"] = _result
                        all_num += 1
                    else:
                        self._log_warning(f"第 {attempt + 1} 次检查执行状态... 未完成")
                        self._log_warning(f"第 {attempt + 1} 次检查执行状态... 结果:{batch_results} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                        break

                if all_num == len(self.google_sheets):
                    self._log_info(f"所有任务已完成")
                    return True, results

                # if attempt in [5,15,25,35]:
                #     for google_sheet in self.google_sheets:
                #         self._log_info(f"向Google Sheet写入参数: {google_sheet.title}")
                #         google_sheet.update_jumped_cells(cell_updates)

            self._log_warning("执行超时，未在规定时间内完成")
            return False, {}

        except Exception as e:
            record = record_task_exception(
                self.task_id,
                e,
                "execute_parameter_combination",
                self.app,
                mark_error=False,
            )
            self._log_error(f"执行参数组合时出错: {format_task_error_message(record)}")
            raise

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool):
        """保存任务结果到数据库，包含重试逻辑"""

        def save_result_operation():
            _index_start_return_date = None
            safe_parameters = self._normalize_result_parameters(parameters)
            safe_result = self._sanitize_json_value(
                self._prepare_result_for_persistence(result)
            )
            task_result = TaskResult(
                task_id=self.task_id,
                step_index=step_index,
                parameters=json.dumps(safe_parameters, allow_nan=False),
                result=json.dumps(safe_result, allow_nan=False),
                success=success
            )
            task_result_repository.add_entity(task_result)
            series_fields = build_return_series_fields(
                extract_return_rows(result),
                stock_code=safe_parameters.get("stock_code"),
                stock_name=safe_parameters.get("stock_name"),
                market_type=self._get_return_series_market_type(safe_parameters),
                exchange_market=self._get_return_series_exchange_market(safe_parameters),
            )
            if series_fields:
                return_series = TaskResultReturn(task_id=self.task_id, **series_fields)
                task_result_repository.add_entity(return_series)
                task_result_repository.flush()
                task_result.return_series_id = return_series.id
            task_result_repository.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_result_operation)
            else:
                from flask import current_app
                with current_app.app_context():
                    safe_db_operation(save_result_operation)
        except Exception as e:
            task_result_repository.rollback()
            error_msg = f"保存任务结果失败: {str(e)}"
            self._log_error(error_msg)
            raise

    def _get_custom_kline_data(
        self,
        input_column_a,
        input_column_b,
        *,
        start_row=2,
        ohlc_columns=None,
    ):
        if not self.google_sheets:
            raise ValueError("自定义K线模式缺少 Google Sheet")

        google_sheet = self.google_sheets[0]
        last_row = google_sheet.get_last_row(input_column_a)
        if last_row < start_row:
            raise ValueError("自定义K线模式下输入列没有K线数据")

        end_column = (ohlc_columns or {}).get("close_column", input_column_b)
        values = google_sheet.get_range(f"{input_column_a}{start_row}:{end_column}{last_row}")
        rows = []
        for row_num in range(start_row, last_row + 1):
            stock_date = values.get(f"{input_column_a}{row_num}")
            if ohlc_columns:
                open_price = values.get(f"{ohlc_columns['open_column']}{row_num}")
                high_price = values.get(f"{ohlc_columns['high_column']}{row_num}")
                low_price = values.get(f"{ohlc_columns['low_column']}{row_num}")
                close_price = values.get(f"{ohlc_columns['close_column']}{row_num}")
                stock_val = close_price
                empty_row = all(value in (None, "") for value in (stock_date, open_price, high_price, low_price, close_price))
            else:
                stock_val = values.get(f"{input_column_b}{row_num}")
                empty_row = stock_date in (None, "") and stock_val in (None, "")
            if empty_row:
                continue
            row = {
                "stock_date": str(stock_date).strip() if stock_date is not None else "",
                "stock_val": stock_val,
            }
            if ohlc_columns:
                row.update({
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                })
            rows.append(row)

        validated = require_kline_rows(
            "custom",
            "custom",
            rows,
            context="自定义K线",
            min_rows=30,
            price_field="stock_val",
        )
        if ohlc_columns:
            self._validate_c7_ohlc_rows(validated)
        return validated

    def _get_custom_parameters(self, parameter, parameters, custom_kline_map):
        data = []
        for v1 in parameters[1]:
            for v2 in parameters[2]:
                data.append({
                    "stock_code": parameter,
                    "A1": v1,
                    "B1": v2,
                    "year": "custom",
                    "Kline_key": "custom",
                })

        if not data:
            raise ValueError(f"股票{parameter} 自定义K线模式下没有可执行参数组合")

        return data, len(custom_kline_map["custom"]) + 20, custom_kline_map

    def _get_all_parameters(self,parameter, count_mode, price_mode, end_date, start_date, market_type,date_range_mode,exclude_recent_years,parameters, adjust_type=None, random_price_range="high_low", random_group_count=1, data_source="dfcf"):

        # random_price 分组展开前先按收盘价占位取价；分组随机取价在 _expand_random_price_groups 里做
        projection_mode = 'sp_price' if price_mode == 'random_price' else price_mode

        _end_year_1 = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        _end_year = int(now_time[:4])
        _start_date = int(start_date[:4])
        limit = (_end_year - _start_date + 1) * 300

        # 旧版 DFCF/Yahoo 分支（原 if market_type... 代码）保留为注释参考。
        # 当前所有任务统一先读内置库，再由 KlineService 按数据源回退外部接口。
        # if market_type == 'cn' or price_mode == 'vwap_price':
        #     stock_config = self.dfcf_api.get_search_list_by_stock_code(parameter, 10)
        #     if market_type in ('us', 'en'):
        #         stock_config = [
        #             i for i in stock_config
        #             if i.get('securityTypeName') == '美股' or str(i.get('market') or '') == '105'
        #         ]
        #
        #     # stock_config = [i for i in stock_config if 'A' in  i['securityTypeName']]
        #     if stock_config:
        #         stock_config = stock_config[0]
        #         try:
        #             upsert_stock_metadata_in_session({
        #                 **stock_config,
        #                 "stock_code": parameter,
        #                 "stock_name": stock_config.get("shortName") or stock_config.get("name"),
        #                 "market_type": market_type,
        #                 "source": stock_config.get("source") or "google_sheet_c7",
        #             })
        #         except Exception as metadata_error:
        #             task_result_repository.rollback()
        #             logger.warning("同步 c7 股票元数据失败: %s", metadata_error)
        #     market = stock_config['market']
        #     stock_name = str(stock_config.get("shortName") or stock_config.get("name") or "").strip()
        #
        #     klines = self.dfcf_api.get_stock_kline_data(parameter, market, limit, adjust_type=adjust_type)
        # else:
        #     klines = self.YF_api.get_kline_data(parameter, '10y', adjust_type=adjust_type)
        #     stock_name = ""
        klines = self.kline_service.get_kline_data(
            parameter,
            market_type,
            limit,
            data_source=data_source,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        stock_name = str(klines[0].get("stock_name") or "") if klines else ""
        parameter = str(klines[0].get("stock_code") or parameter) if klines else parameter
        if stock_name:
            upsert_stock_metadata_in_session({
                "stock_code": parameter,
                "stock_name": stock_name,
                "market_type": market_type,
                "source": "google_sheet_c7",
            })

        price_field = get_kline_price_field(price_mode)
        if price_mode == 'random_price':
            # 随机价格模式的取值字段随 random_price_range 变化，属于 C7 特例
            price_field = 'high' if random_price_range == 'high_low' else 'close'
        klines = require_kline_rows(
            parameter,
            market_type,
            klines,
            context="原始K线",
            min_rows=30,
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
        klines = [
            kline for kline in klines
            if start_date <= kline['stock_date'] <= end_date
        ]
        all_kline = KlineService.build_price_rows(
            klines, projection_mode, start_date=start_date, end_date=end_date, include_ohlc=True
        )
        all_kline = require_kline_rows(
            parameter,
            market_type,
            all_kline,
            context="写入Sheet K线",
            start_date=start_date,
            end_date=end_date,
            latest_date=data_end_date,
        )
        data = []

        KLINE_DATA_MAP = {}
        # for v1 in parameters[1]:
        #     for v2 in parameters[2]:
        #         data.append({'stock_code': parameter, 'kline': all_kline,"A1":v1,"B1":v2})
        #         if count_mode != 'n_plus_1':
        #             continue

        #         if 'recent' in date_range_mode:
        #             for i in range(1, (_end_year_1 - _start_date) + 1):
        #                 _i = i
        #                 if i!=0:
        #                     _i = i - 1

        #                 _end_data = f"{_end_year_1-_i}{end_date[4:]}"
        #                 _start_data = f"{_end_year_1 - i}{end_date[4:]}"
        #                 d = {"A1":v1,"B1":v2}
        #                 kline = _get_kline(klines, _start_data, _end_data)
        #                 if kline:
        #                     d['stock_code'] = parameter
        #                     d['kline'] = kline
        #                     data.append(d)

        #         if 'full' in date_range_mode:
        #             _all_kline = [ k for k in klines if start_date <= k['stock_date'] <= end_date]
        #             for i in range(_start_date, _end_year_1 + 1):
        #                 d = {"A1":v1,"B1":v2}
        #                 kline = _get_kline(_all_kline,_year=i)
        #                 if kline and len(kline) > 30:
        #                     d['stock_code'] = parameter
        #                     d['year'] = i
        #                     d['kline'] = kline
        #                     data.append(d)


        # 在 n+1 模式下，如果勾选了近年，则不生成全部区间（避免重复）
        if count_mode != 'n_plus_1' or 'recent' not in date_range_mode:
            for i, v1 in enumerate(parameters[1]):
                for j, v2 in enumerate(parameters[2]):
                    Kline_key = f'{_end_year_1}-{_start_date}'
                    d = {'stock_code': parameter, "A1": v1, "B1": v2, 'year': Kline_key,'Kline_key':Kline_key}
                    if stock_name:
                        d['stock_name'] = stock_name
                    if Kline_key not in KLINE_DATA_MAP:
                        KLINE_DATA_MAP[Kline_key] = all_kline

                    data.append(d)

        if count_mode != 'n_plus_1':
            data, KLINE_DATA_MAP = self._expand_random_price_groups(
                data, KLINE_DATA_MAP, price_mode, random_price_range, random_group_count
            )
            data = self._deduplicate_parameter_combinations(data, KLINE_DATA_MAP)
            return data, len(all_kline) + 20,KLINE_DATA_MAP

        if 'recent' in date_range_mode:
            # 起止年份差就是可生成的近年区间数量；首尾年份相差 5 年时，
            # 应生成近 1 年到近 5 年，不能额外生成近 6 年的区间。
            total_years = max(0, _end_year_1 - _start_date)
            for year in range(1, total_years + 1):
                # 如果当前年份在排除列表中，跳过
                if year in exclude_recent_years:
                    continue

                # _year = year
                # if year != 0:
                #     _year = year - 1

                _end_data = end_date
                _start_data = max(start_date, f"{_end_year_1 - year}{end_date[4:]}")
                if _start_data > _end_data:
                    continue
                kline = KlineService.build_price_rows(
                    klines, projection_mode, start_date=_start_data, end_date=_end_data, include_ohlc=True
                )
                if not kline:
                    continue
                Kline_key = f"{kline[-1]['stock_date'][:4]}-{kline[0]['stock_date'][:4]}"
                # Kline_key = f'{_end_data[:4]}-{_start_data[:4]}'
                for i, v1 in enumerate(parameters[1]):
                    for j, v2 in enumerate(parameters[2]):
                        d = {"A1": v1, "B1": v2, 'stock_code': parameter, 'year': Kline_key,'Kline_key':Kline_key}
                        if stock_name:
                            d['stock_name'] = stock_name
                        if Kline_key not in KLINE_DATA_MAP:
                            KLINE_DATA_MAP[Kline_key] = kline

                        data.append(d)

        if 'full' in date_range_mode:
            _all_kline = [k for k in klines if start_date <= k['stock_date'] <= end_date]
            for year in range(_start_date, _end_year_1 + 1):
                kline = KlineService.build_price_rows(_all_kline, projection_mode, year=year, include_ohlc=True)
                Kline_key = year
                if not kline:
                    continue

                for i, v1 in enumerate(parameters[1]):
                    for j, v2 in enumerate(parameters[2]):
                        d = {"A1": v1, "B1": v2, 'stock_code': parameter, 'year': year,'Kline_key':Kline_key}
                        if stock_name:
                            d['stock_name'] = stock_name
                        # if i == 0 and j == 0:
                        #     if kline and len(kline) > 30:
                        #         d['kline'] = kline
                        #     else:
                        #         continue
                        if Kline_key not in KLINE_DATA_MAP:
                            KLINE_DATA_MAP[Kline_key] = kline

                        data.append(d)

        data, KLINE_DATA_MAP = self._expand_random_price_groups(
            data, KLINE_DATA_MAP, price_mode, random_price_range, random_group_count
        )

        if not data:
            raise ValueError(
                f"股票{parameter}({market_type}) 在配置区间内没有可执行K线组合，"
                f"请检查 start_date={start_date}, end_date={end_date}, date_range_mode={date_range_mode}"
            )

        data = self._deduplicate_parameter_combinations(data, KLINE_DATA_MAP)
        return data, len(all_kline) + 20,KLINE_DATA_MAP

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
                str(combination.get('random_group', '')),
                str(combination.get('Kline_key', '')) if combination.get('random_group') else '',
                kline_signature,
            )
            if signature in seen:
                self._log_info(
                    "跳过重复 C7 参数组合："
                    f"股票={combination.get('stock_code', '')}，"
                    f"A1={combination.get('A1', '')}，B1={combination.get('B1', '')}，"
                    f"K线区间={kline_signature[0]}~{kline_signature[1]}，"
                    f"行数={kline_signature[2]}"
                )
                continue

            seen.add(signature)
            deduplicated.append(combination)

        return deduplicated

if __name__ == '__main__':
    GoogleSheetService({}, '')._get_all_parameters('588000', 'n_plus_1', 'kp_price','2026-06-10', '2020-11-16', 'cn',
                                                   [
                                                       "recent"
                                                   ],[2, 4, 5, 6],[
    [
        "588000"
    ],
    [
        "",
        3.1,
        3.4,
        3.7,
        4,
        4.3,
        4.5
    ],
    [
        1.5,
        2,
        2.5,
        3,
        3.5,
        4,
        4.5,
        5
    ]
])

