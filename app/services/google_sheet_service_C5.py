import json
import time
from typing import Dict, Any

from flask import current_app
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.exceptions.checkForErrors import checkForErrors
from app.models import Task, TaskResult, db, TaskResultReturn
from app.utils.return_series import build_return_series_fields, extract_return_rows
from app.services.google_sheet_service_base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.services.stock_metadata_service import upsert_stock_metadata_in_session
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation, db_retry_manager
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value
from app.services.xpl_service import xpl_analyzer
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.logger import get_logger
from app.utils.yf_api import YFApi
from app.utils.task_error_utils import unwrap_exception
from app.utils.kline_validation import require_kline_rows
from app.services.kline_service import KlineService, get_kline_price_field


logger = get_logger(__name__)


class GoogleSheetService(BaseGoogleSheetService):
    """Google Sheet服务 - C5"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.google_sheets: list[GoogleSheet] = []
        self.xpl = xpl_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()
        self.kline_service = KlineService(dfcf_api=self.dfcf_api, yahoo_api=self.YF_api)

    @staticmethod
    def _get_resume_start_index(current_step: int | None, total_combinations: int) -> int:
        """返回下一条待执行组合的下标。"""
        return min(max(int(current_step or 0), 0), total_combinations)

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
                task = db.session.get(Task, self.task_id)
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
                task = db.session.get(Task, self.task_id)
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
        analyze_result = result.get('flat_result') if isinstance(result.get('flat_result'), dict) else result

        payload.update({
            "multiplier": combination.get("A1", 0),
            "ml": combination.get("B1"),
            "return_rate": self._to_decimal_ratio(result.get("D2", 0)),
            "annualized_rate": self._to_decimal_ratio(result.get("D3", 0)),
            "maxdd": self._to_decimal_ratio(result.get("D4", 0)),
            "index_rate": self._to_decimal_ratio(result.get("D5", 0)),
            "index_annualized_rate": self._to_decimal_ratio(result.get("D6", 0)),
            "max_index_dd": self._to_decimal_ratio(result.get("D7", 0)),
            "fee_total": self._to_decimal_ratio(result.get("D8", 0)),
            "fee_annualized": self._to_decimal_ratio(result.get("D9", 0)),
            "turnover_rate": result.get("D10", 0),
            "return_beats": self._to_decimal_ratio(result.get("D11", 0)),
            "dd_beats": self._to_decimal_ratio(result.get("D12", 0)),
            "max_1y_beats": self._to_decimal_ratio(result.get("D13", 0)),
            "min_1y_beats": self._to_decimal_ratio(result.get("D14", 0)),
            "max_theoretical_leverage": result.get("D15", 0),
            "avg_theoretical_leverage": result.get("D16", 0),
            "unit_theoretical_leverage_return": self._to_decimal_ratio(result.get("D17", 0)),
            "max_actual_leverage": result.get("D18", 0),
            "avg_actual_leverage": result.get("D19", 0),
            "unit_actual_leverage_return": self._to_decimal_ratio(result.get("D20", 0)),
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
            date_range_mode = config_data.get('date_range_mode',[])
            exclude_recent_years = config_data.get(
                'exclude_recent_years',
                config_data.get('exclude_years', [])
            )
            end_date = config_data.get('end_date')
            start_date = config_data.get('start_date')
            market_type = config_data.get('market_type')
            adjust_type = config_data.get('kline_adjustment')
            c5_input_column_a = config_data.get('c5_input_column_a').upper()
            c5_input_column_b = config_data.get('c5_input_column_b').upper()
            custom_kline_map = None
            if kline_source == 'custom':
                custom_kline = self._get_custom_kline_data(c5_input_column_a, c5_input_column_b)
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
                        outer_param, count_mode, price_mode, end_date, start_date, market_type,date_range_mode,exclude_recent_years,parameters, adjust_type,
                        data_source=config_data.get("kline_data_source", "dfcf")
                    )
                precomputed_params.append((combinations, column_A_length,KLINE_DATA_MAP))
                total_combinations += len(combinations)

            # 更新任务总步数
            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

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
                    A_num = google_sheet.get_last_row('A')
                    if A_num < 10:
                        continue
                    self._log_info(f'{google_sheet.title} 当前A列行数: {A_num},准备滞空 A列 B列')
                    google_sheet.clear_range(f"{c5_input_column_a}2:{c5_input_column_b}{A_num+2}")

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
                        return db.session.query(Task.status).filter(
                            Task.id == self.task_id
                        ).first()

                    result = safe_db_operation(check_task_status)

                    if not result or result.status == 'cancelled':
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
                        db_retry_manager.commit_with_retry(db.session)

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
                            task_check = db.session.get(Task, self.task_id)
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
            # 检查是否是任务被取消导致的异常
            task.error = e
            try:
                task_check = db.session.get(Task, self.task_id)
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
            # 获取参数位置配置
            c5_input_column_a = config_data.get('c5_input_column_a').upper()
            c5_input_column_b = config_data.get('c5_input_column_b').upper()

            c5_output_range_1 = config_data.get('c5_output_range_1')
            c5_output_range_2 = config_data.get('c5_output_range_2')
            c5_parameter_positions = config_data.get('c5_parameter_positions')
            c5_output_column_j = config_data.get('c5_output_column_j')
            c5_output_column_l = config_data.get('c5_output_column_l')
            c5_check_positions = config_data.get('c5_check_positions')

            initial_results = {}

            results = {}
            cell_updates = {}
            c5_parameter_1 = f"xm:{combination[c5_parameter_positions[0]]}"
            c5_parameter_2 = f"ml:{combination[c5_parameter_positions[1]]}"
            cell_updates[c5_parameter_positions[0]] = c5_parameter_1
            cell_updates[c5_parameter_positions[1]] = c5_parameter_2
            Kline_key = combination['Kline_key']
            is_custom_kline = str(config_data.get('kline_source') or 'auto').strip().lower() == 'custom'
            current_kline = require_kline_rows(
                combination.get('stock_code', ''),
                config_data.get('market_type', ''),
                KLINE_DATA_MAP.get(Kline_key),
                context=f"K线区间 {Kline_key}",
            )

            def set_googl_val(initial_result_sleep=None):
                _combination = cache_parameters['combination']
                cache_Kline_key = _combination.get('Kline_key',"")
                kline = current_kline
                _kline_len = len(kline)

                if is_custom_kline:
                    self._log_info(f"自定义K线模式，不修改K线列，只写入参数 combination:{combination}")
                elif Kline_key != cache_Kline_key or initial_result_sleep is not None:
                    for google_sheet in self.google_sheets:
                        # A_num = google_sheet.get_last_row('A')
                        A_num = column_A_length
                        self._log_info(f'{google_sheet.title} 当前A列行数: {A_num},预写入长度：{_kline_len} 准备滞空 A列 B列')
                        google_sheet.clear_range(f"{c5_input_column_a}2:{c5_input_column_b}{A_num+2}")

                    # 准备要更新的单元格
                    for i in range(_kline_len):
                        item = {}
                        if i <= _kline_len:
                            item = kline[i]
                        cell_num = i + 2
                        cell_A = f"{c5_input_column_a}{cell_num}"
                        cell_B = f"{c5_input_column_b}{cell_num}"
                        stock_date = item.get('stock_date', "")
                        stock_val = item.get('stock_val', "")
                        cell_updates[cell_A] = stock_date
                        cell_updates[cell_B] = stock_val

                else:
                    self._log_info(f"同源数据，不需要修改k线，改动参数就行 combination:{combination},cache_parameters:{cache_parameters}")

                if initial_result_sleep:
                    self._log_info(f"刷新参数等待：{initial_result_sleep}秒")
                    if not self._interruptible_sleep(initial_result_sleep):
                        raise RuntimeError("task cancelled")

                for google_sheet in self.google_sheets:
                    initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c5_output_range_1)

                for google_sheet in self.google_sheets:
                    self._log_info(f"向Google Sheet写入参数: {google_sheet.title} 长度：{len(cell_updates)}")
                    google_sheet.update_jumped_cells(cell_updates)

            set_googl_val()
            kline = current_kline

            def check_result(check_values):
                _check_values = {}
                for _position, _value in check_values.items():
                    if not _value or not is_valid_result_value(_value):
                        self._log_info(f"结果位置 {_position} 值为空或无效，跳过重新检查：{_value}")
                        raise Exception(f"结果位置 {_position} 值为空或无效，跳过重新检查：{_value}")

                    if str(_value).strip().startswith(("#", "#N/A")):
                        _error_msg = f"获取结果位置 {_position} 时出错: {str(_value)}"
                        raise checkForErrors(f"检查报错，出现#|#N/A 这种异常错误，联系用户检查 {_error_msg}")

                    if '%' in _value:
                        _value = float(_value.replace('%', '').replace(',', '')) / 100
                    if isinstance(_value, str) and ',' in _value:
                        _value = float(_value.replace(',', ''))
                    if _value == '-':
                        continue
                    _check_values[_position] = _value
                return _check_values

            def _validate_check_values(check_values: Dict[str, Any], spreadsheet_id) -> bool:
                """验证检查位置的值是否有效"""
                if not check_values:
                    return False
                c5_check_positions_c_v = check_values.get(":".join(c5_check_positions))
                c5_output_range_1_c_v = check_values.get(c5_output_range_1)
                # for position, value in check_values.items():
                #     if not value or value in ['#DIV/0!', '', '#N/A', '#ERROR!', '#VALUE!']:
                #         return False
                #     if 'target' in str(value).lower():
                #         return False
                _check_values = initial_results[spreadsheet_id]

                if (c5_parameter_1.strip() != c5_check_positions_c_v.get(c5_check_positions[0]).strip()
                        and c5_parameter_2.strip() != c5_check_positions_c_v.get(c5_check_positions[1]).strip()):
                    # 校验参数是否成功响应
                    self._log_info(f"c5_parameter_1:{c5_parameter_1} != {c5_check_positions[0]}{c5_check_positions_c_v.get(c5_check_positions[0]).strip()} "
                                   f"c5_parameter_2:{c5_parameter_2} != {c5_check_positions[1]}{c5_check_positions_c_v.get(c5_check_positions[1]).strip()}")
                    return False

                _check_values = initial_results[spreadsheet_id]

                if (_check_values[f'{c5_output_range_1[0]}2'] == c5_output_range_1_c_v[f'{c5_output_range_1[0]}2']
                        and _check_values[f'{c5_output_range_1[0]}3'] == c5_output_range_1_c_v[f'{c5_output_range_1[0]}3']):
                    return False

                return True

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
                    # _result = google_sheet.get_range(c5_output_range_1)
                    _result = {}
                    batch_results = google_sheet.get_ranges([c5_output_range_1,":".join(c5_check_positions)])
                    if _validate_check_values(batch_results, google_sheet.spreadsheet_id):
                        _result.update(batch_results.get(c5_output_range_1, {}))
                        _result['result_parameters'] = batch_results.get(":".join(c5_check_positions))

                        # # _result = check_result(_result)
                        # _result_yearly = google_sheet.get_range(c5_output_range_2)
                        # # _result_yearly = check_result(google_sheet.get_range(c5_output_range_2))
                        # _result.update(_result_yearly)
                        #
                        # try:
                        #     _index_return = check_result(
                        #         google_sheet.get_range(f"{c5_output_column_j}2:{c5_output_column_j}{len(kline) + 1}")
                        #     )
                        #     _start_return = check_result(
                        #         google_sheet.get_range(f"{c5_output_column_l}2:{c5_output_column_l}{len(kline) + 1}")
                        #     )
                        # except Exception as e:
                        #     self._log_info(f"获取结果位置 {c5_output_column_j}2:{c5_output_column_j}{len(kline) + 1} 时出错：{str(e)}")
                        #     self._log_info(f"_result：{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                        #     break
                        # _result = check_result(_result)
                        merged_return_range_a1 = f"{c5_output_column_j}2:{c5_output_column_l}{len(kline) + 1}"
                        batch_range_values = google_sheet.get_ranges([
                            c5_output_range_2,
                            merged_return_range_a1,
                        ])
                        _result_yearly = batch_range_values.get(c5_output_range_2, {})
                        # _result_yearly = check_result(google_sheet.get_range(c5_output_range_2))
                        _result.update(_result_yearly)

                        try:
                            merged_return_range = batch_range_values.get(merged_return_range_a1, {})
                            _index_return = check_result({
                                position: value
                                for position, value in merged_return_range.items()
                                if position.startswith(c5_output_column_j)
                            })
                            _start_return = check_result({
                                position: value
                                for position, value in merged_return_range.items()
                                if position.startswith(c5_output_column_l)
                            })
                        except Exception as e:
                            self._log_info(f"获取结果位置 {c5_output_column_j}2:{c5_output_column_l}{len(kline) + 1} 时出错：{str(e)}")
                            self._log_info(f"_result：{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                            break

                        _index_return_date = []
                        _start_return_date = []
                        _return_data = []
                        _index_start_return_date = []
                        for i in range(len(kline)):
                            # _index_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _index_return[f"{c5_output_column_j}{i + 2}"]
                            # })
                            # _start_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _start_return[f"{c5_output_column_l}{i + 2}"]
                            # })
                            _return_data.append({
                                'date': kline[i].get('stock_date'),
                                'index_return': _index_return[f"{c5_output_column_j}{i + 2}"],
                                'start_return': _start_return[f"{c5_output_column_l}{i + 2}"]
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
                        # results[f"flat_result"] = flat_result
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
            db.session.add(task_result)
            series_fields = build_return_series_fields(
                extract_return_rows(result),
                stock_code=safe_parameters.get("stock_code"),
                stock_name=safe_parameters.get("stock_name"),
                market_type=self._get_return_series_market_type(safe_parameters),
                exchange_market=self._get_return_series_exchange_market(safe_parameters),
            )
            if series_fields:
                return_series = TaskResultReturn(task_id=self.task_id, **series_fields)
                db.session.add(return_series)
                db.session.flush()
                task_result.return_series_id = return_series.id
            db.session.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_result_operation)
            else:
                from flask import current_app
                with current_app.app_context():
                    safe_db_operation(save_result_operation)
        except Exception as e:
            db.session.rollback()
            error_msg = f"保存任务结果失败: {str(e)}"
            self._log_error(error_msg)
            raise

    def _get_custom_kline_data(self, input_column_a, input_column_b):
        if not self.google_sheets:
            raise ValueError("自定义K线模式缺少 Google Sheet")

        google_sheet = self.google_sheets[0]
        last_row = google_sheet.get_last_row(input_column_a)
        if last_row < 2:
            raise ValueError("自定义K线模式下输入列没有K线数据")

        values = google_sheet.get_range(f"{input_column_a}2:{input_column_b}{last_row}")
        rows = []
        for row_num in range(2, last_row + 1):
            stock_date = values.get(f"{input_column_a}{row_num}")
            stock_val = values.get(f"{input_column_b}{row_num}")
            if stock_date in (None, "") and stock_val in (None, ""):
                continue
            rows.append({
                "stock_date": str(stock_date).strip() if stock_date is not None else "",
                "stock_val": stock_val,
            })

        return require_kline_rows(
            "custom",
            "custom",
            rows,
            context="自定义K线",
            min_rows=30,
            price_field="stock_val",
        )

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

        data = self._deduplicate_parameter_combinations(data, custom_kline_map)
        return data, len(custom_kline_map["custom"]) + 20, custom_kline_map

    def _get_all_parameters(self,parameter, count_mode, price_mode, end_date, start_date, market_type,date_range_mode,exclude_recent_years,parameters, adjust_type=None, data_source="dfcf"):

        _end_year_1 = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        _end_year = int(now_time[:4])
        _start_date = int(start_date[:4])
        limit = (_end_year - _start_date + 1) * 300

        # 旧版 DFCF/Yahoo 分支（原 if market_type... 代码）保留在版本历史中，
        # 当前所有任务统一通过 KlineService：先读内置库，再按数据源回退外部接口。
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
        #                 "source": stock_config.get("source") or "google_sheet_c5",
        #             })
        #         except Exception as metadata_error:
        #             db.session.rollback()
        #             logger.warning("同步 C5 股票元数据失败: %s", metadata_error)
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
                "source": "google_sheet_c5",
            })

        price_field = get_kline_price_field(price_mode)
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
        # # 检查用户设定的区间是否在数据范围内
        # if start_date < data_start_date or end_date > data_end_date:
        #     raise Exception(
        #         f"股票{parameter} 设定区间 [{start_date}, {end_date}] 不在K线数据范围 [{data_start_date}, {data_end_date}] 内")

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
        all_kline = self.kline_service.build_price_rows(
            klines, price_mode, start_date=start_date, end_date=end_date
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
                kline = self.kline_service.build_price_rows(
                    klines, price_mode, start_date=_start_data, end_date=_end_data
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
                kline = self.kline_service.build_price_rows(_all_kline, price_mode, year=year)
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
                kline_signature,
            )
            if signature in seen:
                self._log_info(
                    "跳过重复 C5 参数组合："
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

