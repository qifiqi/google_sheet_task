import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional,Tuple

from flask import current_app
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.exceptions.checkForErrors import checkForErrors
from app.models import Task, TaskResult, db
from app.services.google_sheet_service_base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.services.xpl_service import xpl_analyzer
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation, db_retry_manager
from app.utils.dfcf_api import DFCJStockApi
from app.utils.logger import get_logger
from app.utils.result_validator import validate_result_dict, validate_google_sheet_result, is_valid_result_value
from app.utils.yf_api import YFApi
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.task_error_utils import unwrap_exception
from app.utils.kline_validation import require_kline_rows

logger = get_logger(__name__)


class GoogleSheetService(BaseGoogleSheetService):
    """Google Sheet服务"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.klines_map = None
        self.kline = None
        self.len_kline = None
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()
        self.google_sheet:Optional[GoogleSheet] = None
        self.xpl = xpl_analyzer

    def _build_parameter_cell_updates(
        self,
        combination: List[Any],
        param_positions: List[str],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        cell_updates: Dict[str, Any] = {}
        results: Dict[str, Any] = {}
        for index, position in enumerate(param_positions):
            value = combination[index]
            cell_updates[position] = value
            results[position] = value
        return cell_updates, results

    def _write_parameter_cells(self, cell_updates: Dict[str, Any], attempt: int = 0,config_data=None):
        if attempt <= 0:
            self._log_info(f"向Google Sheet写入参数: {cell_updates}")
            self.google_sheet.update_jumped_cells(cell_updates)
            return

        self._log_info(
            "模型可能卡死，直接清空参数，等待20s后重新写入参数，请稍等..."
        )

        if attempt >= 10 and not self.klines_map:
            c3_input_column_d = config_data.get('c3_input_column_d').upper()
            c3_input_column_e = config_data.get('c3_input_column_e').upper()
            A_num = self.len_kline + random.randint(5, 10)
            self._log_info(f'{self.google_sheet.title} 当前D列行数: {A_num},准备滞空 D列 E列')
            self.google_sheet.clear_range(f"{c3_input_column_d}2:{c3_input_column_e}{A_num + 2}")

            self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
            if not self._interruptible_sleep(20):
                raise RuntimeError("task cancelled")

            for i in range(self.len_kline):
                item = self.klines_map[i]
                cell_num = i + 2
                cell_A = f"{c3_input_column_d}{cell_num}"
                cell_B = f"{c3_input_column_e}{cell_num}"
                stock_date = item.get('stock_date', "")
                stock_val = item.get('stock_val', "")
                cell_updates[cell_A] = stock_date
                cell_updates[cell_B] = stock_val
            self.google_sheet.update_jumped_cells(cell_updates)
            return

        self.google_sheet.clear_jumped_cells(cell_updates.keys())
        if not self._interruptible_sleep(20):
            raise RuntimeError("task cancelled")

        self.google_sheet.update_jumped_cells(cell_updates)

        

        # random_key = random.choice(list(cell_updates.keys()))
        # random_value = cell_updates[random_key]
        # self._log_info(
        #     f"防止模型卡顿，在随机位置写入：{random_key} = {random_value} "
        #     f"(类型: {type(random_value)}),当前是第{attempt + 1}轮检查"
        # )

        # if random_value is None or str(random_value).strip() == "":
        #     self._log_warning(f"跳过写入空值到位置 {random_key}")
        #     return

        # try:
        #     self.google_sheet.update_cell(random_key, str(random_value))
        # except Exception as err:
        #     self._log_error(f"更新单元格 {random_key} 失败，值: {random_value}, 错误: {err}")
        #     raise

    def _normalize_result_value(self, position: str, value: Any) -> float:
        if not value or not is_valid_result_value(value):
            self._log_info(f"结果位置 {position} 值为空或无效，跳过重新检查")
            raise Exception(f"结果位置 {position} 值为空或无效，跳过重新检查")

        raw_value = str(value).strip()
        if raw_value.startswith(("#", "#N/A")):
            error_msg = f"获取结果位置 {position} 时出错: {raw_value}"
            raise checkForErrors(f"检查报错，出现#|#N/A 这种异常错误，联系用户检查 {error_msg}")

        if '%' in raw_value:
            return round(float(raw_value.replace('%', '').replace(',', '')) / 100, 5)
        if isinstance(value, str):
            return round(float(raw_value.replace(',', '')), 5)
        return round(float(value), 5)

    def _validate_check_values(self, check_values: Dict[str, Any], input_results: Dict[str, Any]) -> bool:
        if not check_values:
            return False

        for position, value in check_values.items():
            if not value or value in ['#DIV/0!', '', '#N/A', '#ERROR!', '#VALUE!']:
                return False
            if 'target' in str(value).lower():
                return False

            input_key = f"B{position[1:]}"
            if input_key not in input_results:
                continue

            try:
                check_value = float(value.replace('%', '')) / 100 if '%' in value else float(value)
                input_value = float(input_results[input_key])
                if round(check_value) != round(input_value):
                    return False
            except (ValueError, TypeError):
                return False

        return True

    def _validate_result_values(
        self,
        result_values: Dict[str, Any],
        result_positions: List[str],
    ) -> Tuple[bool, List[str]]:
        if not result_values:
            return False, ["结果字典为空"]

        missing_positions = []
        invalid_positions = []
        for position in result_positions:
            if position not in result_values:
                missing_positions.append(position)
                continue

            value = result_values[position]
            if not is_valid_result_value(value):
                invalid_positions.append(f"{position}({value})")

        error_messages = []
        if missing_positions:
            error_messages.append(f"缺少位置: {missing_positions}")
        if invalid_positions:
            error_messages.append(f"无效值: {invalid_positions}")

        return len(error_messages) == 0, error_messages

    def _finalize_result_values(
        self,
        result_values: Dict[str, Any],
        result_positions: List[str],
        base_results: Dict[str, Any],
        config_data: Dict[str, Any],
    ) -> tuple[bool, Dict[str, Any]]:
        final_results = dict(base_results)
        for position in result_positions:
            final_results[position] = self._normalize_result_value(position, result_values.get(position, ""))

        analysis_payload = self._attach_return_analysis(config_data)
        if analysis_payload:
            final_results.update(analysis_payload)

        is_valid, error_msg = validate_google_sheet_result(final_results)
        if not is_valid:
            self._log_warning(f"Google Sheet结果验证失败: {error_msg}")
            return False, {}
        return True, final_results

    def _try_get_batch_results(
        self,
        result_positions: List[str],
        base_results: Dict[str, Any],
        config_data: Dict[str, Any],
    ) -> tuple[bool, Dict[str, Any]]:
        result_values = self.google_sheet.get_cells_batch(result_positions)
        self._log_info(f"获取到参数执行结果: {result_values}")

        is_valid, error_messages = self._validate_result_values(result_values, result_positions)
        if not is_valid:
            self._log_warning(f"结果验证失败: {error_messages}，继续等待...")
            return False, {}

        return self._finalize_result_values(result_values, result_positions, base_results, config_data)

    def _try_get_fallback_results(
        self,
        result_positions: List[str],
        base_results: Dict[str, Any],
        config_data: Dict[str, Any],
    ) -> tuple[bool, Dict[str, Any]]:
        fallback_values: Dict[str, Any] = {}
        for position in result_positions:
            try:
                fallback_values[position] = self.google_sheet.get_cell(position)
            except Exception as err:
                self._log_error(f"获取结果位置 {position} 时出错: {err}")
                return False, {}

        success, final_results = self._finalize_result_values(
            fallback_values,
            result_positions,
            base_results,
            config_data,
        )
        if not success:
            self._log_warning("回退模式结果验证失败")
            return False, {}
        return True, final_results

    def _build_return_analysis_input(self, config_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.google_sheet or not self.len_kline:
            return []

        date_column = str(config_data.get('c3_input_column_d') or '').upper()
        index_column = str(config_data.get('c3_output_column_K') or '').upper()
        start_column = str(config_data.get('c3_output_column_O') or '').upper()
        if not date_column or not index_column or not start_column:
            return []

        end_row = int(self.len_kline) + 1
        date_range = f"{date_column}2:{date_column}{end_row}"
        index_range = f"{index_column}2:{index_column}{end_row}"
        start_range = f"{start_column}2:{start_column}{end_row}"

        batch_values = self.google_sheet.get_ranges([date_range, index_range, start_range])
        date_values = batch_values.get(date_range, {})
        index_values = batch_values.get(index_range, {})
        start_values = batch_values.get(start_range, {})

        return_data = []
        for row_num in range(2, end_row + 1):
            date_value = date_values.get(f"{date_column}{row_num}")
            index_value = index_values.get(f"{index_column}{row_num}")
            start_value = start_values.get(f"{start_column}{row_num}")
            if date_value in (None, '') or index_value in (None, '') or start_value in (None, ''):
                continue

            try:
                return_data.append({
                    "date": str(date_value).strip(),
                    "index_return": self._normalize_result_value(f"{index_column}{row_num}", index_value),
                    "start_return": self._normalize_result_value(f"{start_column}{row_num}", start_value),
                })
            except checkForErrors:
                raise
            except Exception as err:
                self._log_warning(f"跳过收益分析行 {row_num}: {err}")

        return return_data

    def _attach_return_analysis(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return_data = self._build_return_analysis_input(config_data)
            if not return_data or not self.xpl:
                return {}

            flat_result, analyze_result = self.xpl.get_return_analysis_v1(return_data)
            progress_msg = f'收益率分析执行完成，结果如下：{analyze_result}'
            self._log_info(progress_msg)
            return {
                "analyze_result": analyze_result,
                "flat_result": flat_result,
            }
        except checkForErrors:
            raise
        except Exception as err:
            self._log_warning(f"收益分析附加失败: {err}")
            return {}

    def _build_stock_param_result_payload(
        self,
        task_name: str,
        task_index: int,
        config_data: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = self._build_stock_param_result_base_payload(task_name, task_index, config_data)
        return_analysis = result.get("flat_result") if isinstance(result.get("flat_result"), dict) else result
        payload.update({
            "multiplier": result.get("B6", 0),
            "danbian": result.get("B7", 0),
            "xiancang": result.get("B9", 0),
            "zhishu": result.get("B10", 0),
            "smoothing": result.get("B11", 0),
            "bordering": result.get("B12", 0),
            "return_rate": result.get("I15", 0),
            "annualized_rate": result.get("I16", 0),
            "maxdd": result.get("I17", 0),
            "index_rate": result.get("I18", 0),
            "index_annualized_rate": result.get("I19", 0),
            "max_index_dd": result.get("I20", 0),
            "fee_total": result.get("I21", 0),
            "fee_annualized": result.get("I22", 0),
            "year_rate": result.get("I23", 0),
            "turnover_rate": result.get("turnover_rate", 0),
            "return_beats": result.get("return_beats", 0),
            "dd_beats": result.get("dd_beats", 0),
            "max_1y_beats": result.get("max_1y_beats", 0),
            "min_1y_beats": result.get("min_1y_beats", 0),
            "max_theoretical_leverage": result.get("max_theoretical_leverage", 0),
            "avg_theoretical_leverage": result.get("avg_theoretical_leverage", 0),
            "unit_theoretical_leverage_return": result.get("unit_theoretical_leverage_return", 0),
            "max_actual_leverage": result.get("max_actual_leverage", 0),
            "avg_actual_leverage": result.get("avg_actual_leverage", 0),
            "unit_actual_leverage_return": result.get("unit_actual_leverage_return", 0),
            "start_monthly_std_dev": return_analysis.get("start_monthly_std_dev", 0),
            "index_monthly_std_dev": return_analysis.get("index_monthly_std_dev", 0),
            "index_annualized_return": return_analysis.get("index_annualized_return", 0),
            "start_annualized_return": return_analysis.get("start_annualized_return", 0),
            "index_profit_annual": return_analysis.get("index_profit_annual", 0),
            "start_profit_annual": return_analysis.get("start_profit_annual", 0),
            "index_profit_monthly_percentage": return_analysis.get("index_profit_monthly_percentage", 0),
            "start_profit_monthly_percentage": return_analysis.get("start_profit_monthly_percentage", 0),
            "index_avg_monthly_return_common": return_analysis.get("index_avg_monthly_return_common", 0),
            "start_avg_monthly_return_common": return_analysis.get("start_avg_monthly_return_common", 0),
            "index_monthly_return_volatility": return_analysis.get("index_monthly_return_volatility", 0),
            "start_monthly_return_volatility": return_analysis.get("start_monthly_return_volatility", 0),
            "annualized_return_diff": return_analysis.get("annualized_return_diff", 0),
            "outperform_year": return_analysis.get("outperform_year", 0),
            "monthly_excess_return_percentage_last_return": return_analysis.get(
                "monthly_excess_return_percentage_last_return",
                0,
            ),
            "avg_monthly_excess_returns": return_analysis.get("avg_monthly_excess_returns", 0),
            "monthly_excess_volatility": return_analysis.get("monthly_excess_volatility", 0),
            "max_drawdown": return_analysis.get("max_drawdown", 0),
            "excess_drawdown_winning_rate": return_analysis.get("excess_drawdown_winning_rate", 0),
            "start_drawdown": return_analysis.get("start_drawdown", 0),
            "start_maximum_number_of_backtest_repair_days": return_analysis.get(
                "start_maximum_number_of_backtest_repair_days",
                0,
            ),
            "excess_maximum_number_of_backtest_repair_days": return_analysis.get(
                "excess_maximum_number_of_backtest_repair_days",
                0,
            ),
            "index_sharpe_ratio": return_analysis.get("index_sharpe_ratio", 0),
            "start_sharpe_ratio": return_analysis.get("start_sharpe_ratio", 0),
            "index_kama_ratio": return_analysis.get("index_kama_ratio", 0),
            "start_kama_ratio": return_analysis.get("start_kama_ratio", 0),
            "index_sotino_ratio": return_analysis.get("index_sotino_ratio", 0),
            "start_sotino_ratio": return_analysis.get("start_sotino_ratio", 0),
            "excess_sharp": return_analysis.get("excess_sharp", 0),
            "excess_of_promissory_note": return_analysis.get("excess_of_promissory_note", 0),
        })
        return payload

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
                if self._is_cancel_requested():
                    self._log_info(f'task {self.task_id} cancellation requested')
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
                sheet_name = config_data.get('sheet_name', "")

                # 检查任务是否已被取消
                if task.status == 'cancelled':
                    self._log_info(f'任务 {self.task_id} 已被取消，停止执行')
                    return 'cancelled'
                if self._is_cancel_requested():
                    self._log_info(f'task {self.task_id} cancellation requested')
                    return 'cancelled'

                # stock_param = self.get_single_stock_template_param(name)
                stock_param = None
                if stock_param is not None and stock_param != "error":
                    multiplier_index = 0 if stock_param.get('multiplier_index', 0) == 0 else stock_param.get(
                        'multiplier_index', 0) + 1
                    self._log_info(f"开始执行参数批量处理，multiplier_index: {multiplier_index}")
                    success_count, failed_count, task_status = self.get_bdl(task, name, parameters, config_data, multiplier_index)
                elif stock_param != "error":
                    self._log_info("开始执行参数批量处理（默认参数模式）")
                    success_count, failed_count, task_status = self.get_bdl(task, name, parameters, config_data,task.current_step)
                else:
                    self._log_error("获取股票参数失败")
                    return 'error'

                # 根据任务状态决定返回结果
                if task_status == 'cancelled':
                    # 任务被取消，保持cancelled状态
                    self._log_info(f'任务已取消，成功执行: {success_count}, 失败: {failed_count}')
                    # # 推送任务取消通知
                    # self.task_ok_to_dd(f'任务已取消！成功执行: {success_count}, 失败: {failed_count}')
                    return 'cancelled'
                elif task_status == 'error':
                    return 'error'
                else:
                    if stock_param is not None and stock_param != "error":
                        final_status = 'completed' if success_count > 0 else 'error'
                        if final_status == 'completed':
                            self._refresh_model_summary_index()
                            # 推送成功完成通知
                            self.task_ok_to_dd(f'任务成功完成！成功执行: {success_count}, 失败: {failed_count}')
                        return final_status

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
                logger.warning("记录任务异常失败: %s", record_error)
                error_summary = f"{root.__class__.__name__}: {root}"
            error_msg = f"执行Google Sheet任务失败: {self.task_id}, 错误: {str(root)}"
            self._log_error(error_msg)
            self._log_error(f"任务异常摘要: {error_summary}")
            return 'error'

    def cell_kline_data(self,config_data):
        stock_code = config_data.get('stock_code', '')
        year_n = config_data.get('year_n', '1y')
        # count_mode = config_data.get('count_mode', 'n_plus_1')
        price_mode = config_data.get('price_mode', 'sp_price')
        end_date = config_data.get('end_date')
        market_type = config_data.get('market_type','cn')
        adjust_type = config_data.get('kline_adjustment')
        C3_commission_cell = config_data.get('C3_commission_cell','B5')

        c3_input_column_d = config_data.get('c3_input_column_d').upper()
        c3_input_column_e = config_data.get('c3_input_column_e').upper()



        def _get_kline(klines, _year=None, _start_date_1=None, _end_date_1=None):
            # klines 里假设 'stock_date' 也是 'YYYY-MM-DD' 字符串
            # 根据price_mode决定使用开盘价、收盘价或加权平均价
            price_field = {
                'kp_price': 'stock_kp',
                'vwap_price': 'stock_vwap',
            }.get(price_mode, 'stock_sp')

            if market_type == 'cn':
                if _year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k.get(price_field, k.get('stock_sp'))}
                        for k in klines if int(k['stock_date'][:4]) == _year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k.get(price_field, k.get('stock_sp'))}
                    for k in klines
                    if _start_date_1 <= k['stock_date'] <= _end_date_1
                ]
            else:
                if _year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k.get(price_field, k.get('stock_sp'))}
                        for k in klines if int(k['stock_date'][:4]) == _year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k.get(price_field, k.get('stock_sp'))}
                    for k in klines
                    if _start_date_1 <= k['stock_date'] <= _end_date_1
                ]

        year_text = str(year_n or '1y').strip().lower()
        year_count = 1
        if year_text.endswith('y'):
            try:
                year_count = max(1, int(year_text[:-1]))
            except ValueError:
                year_count = 1

        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            
        start_dt = end_dt - timedelta(days=365 * year_count)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

        # A股按交易日粗略估算每年约 250 个交易日，美股按约 252 个交易日，额外留一点缓冲。
        trading_days_per_year = 250 if market_type == 'cn' else 252
        limit = max(300, year_count * trading_days_per_year + 80)

        if market_type == 'cn':
            stock_config = self.dfcf_api.get_search_list_by_stock_code(stock_code, 10)
            # stock_config = [i for i in stock_config if i['securityTypeName'] == '美股']

            # stock_config = [i for i in stock_config if 'A' in  i['securityTypeName']]
            if stock_config:
                stock_config = stock_config[0]
            market = stock_config['market']

            klines = self.dfcf_api.get_stock_kline_data(stock_code, market, limit, adjust_type=adjust_type)
        else:
            klines = self.YF_api.get_kline_data(stock_code, '10y', adjust_type=adjust_type)

        klines = require_kline_rows(
            stock_code,
            market_type,
            klines,
            context="原始K线",
            min_rows=100,
            price_field='stock_kp' if price_mode == 'kp_price' else 'stock_sp',
        )

        # 获取K线数据的时间范围
        data_start_date = klines[0]['stock_date']
        data_end_date = klines[-1]['stock_date']

        # 如果设定的起始日期早于K线最早日期，则使用K线最早日期
        if start_date < data_start_date:
            self._log_info(
                f"股票{stock_code} 设定区间起点 {start_date} 早于K线首日 {data_start_date}，"
                f"将从K线首日开始执行"
            )
            start_date = data_start_date

        # 检查结束日期是否超出K线数据范围
        if end_date > data_end_date:
            raise Exception(
                f"股票{stock_code} 设定区间 [{start_date}, {end_date}] 不在K线数据范围 [{data_start_date}, {data_end_date}] 内")

        all_kline = _get_kline(klines, _start_date_1=start_date, _end_date_1=end_date)
        all_kline = require_kline_rows(
            stock_code,
            market_type,
            all_kline,
            context="写入Sheet K线",
            start_date=start_date,
            end_date=end_date,
            latest_date=data_end_date,
            min_rows=1,
        )

        sxf = '0.035%' if market_type == 'cn' else '0.002%'
        cell_updates = {C3_commission_cell: sxf}
        len_kline = len(all_kline)
        self.len_kline = len_kline
        self.kline = [all_kline[0],all_kline[-1]]
        self.klines_map = all_kline
        for i in range(len_kline):
            item = all_kline[i]
            cell_num = i + 2
            cell_A = f"{c3_input_column_d}{cell_num}"
            cell_B = f"{c3_input_column_e}{cell_num}"
            stock_date = item.get('stock_date', "")
            stock_val = item.get('stock_val', "")
            cell_updates[cell_A] = stock_date
            cell_updates[cell_B] = stock_val
        self.google_sheet.update_jumped_cells(cell_updates)


        pass

    def get_bdl(self, task, name, parameters, config_data, index_z=0):
        """执行批量数据处理"""
        try:
            # 计算总参数组合数（不生成实际组合，避免内存问题）
            total_combinations = 1
            for param_list in parameters:
                total_combinations *= len(param_list)

            # 更新任务总步数
            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

            # 推送参数组合信息
            self._log_info(f'将执行 {total_combinations} 个参数组合')

            # 执行参数组合
            success_count = 0
            failed_count = 0
            if index_z > total_combinations:
                self._log_warning(f'任务数据库内条数:{index_z} > 参数组合条数:{total_combinations}，跳过执行,好像执行过的')
                return 0, 0, 'completed'


            # 检查是否从断点恢复
            start_index = max(index_z, task.current_step - 1) if task.current_step >= 1 else index_z
            self._log_info(f"任务将从第 {start_index + 1} 个参数组合开始执行")
            success_count = start_index # 成功执行计数器，从断点除重新来

            c3_input_column_d = config_data.get('c3_input_column_d').upper()
            c3_input_column_e = config_data.get('c3_input_column_e').upper()
            stock_code = config_data.get("stock_code",'')
            if stock_code:
                A_num = self.google_sheet.get_last_row('D')
                if A_num > 10:
                    self._log_info(f'{self.google_sheet.title} 当前D列行数: {A_num},准备滞空 D列 E列')
                    self.google_sheet.clear_range(f"{c3_input_column_d}2:{c3_input_column_e}{A_num+2}")

                    self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
                    if not self._interruptible_sleep(20):
                        return success_count, failed_count, 'cancelled'

                self.cell_kline_data(config_data)
            else:
                A_num = self.google_sheet.get_last_row('D')
                _result = self.google_sheet.get_range(f"D2:E{A_num}")
                self.kline = [{"stock_date": _result.get("D2"), "stock_val": _result.get("E2")},
                              {"stock_date": _result.get(f"D{A_num}"), "stock_val": _result.get(f"E{A_num}")}]
                self.len_kline = A_num
                self._log_info(f'获取表格数据成功，行数: {A_num},开始执行后续逻辑 K线范围：{self.kline}')

            for i in range(start_index, total_combinations):
                if self._is_cancel_requested():
                    self._log_warning("task cancellation requested")
                    return success_count, failed_count, 'cancelled'
                self._log_step(i + 1, total_combinations, f"开始执行参数组合")
                
                # 按需计算参数组合，避免内存问题
                combination = self._get_parameter_combination_by_index(parameters, i)
                
                # 原子性检查任务是否被取消
                # SQLite不支持FOR UPDATE，使用简单查询
                def check_task_status():
                    return db.session.execute(
                        text("SELECT status FROM tasks WHERE id = :task_id"),
                        {"task_id": self.task_id}
                    ).fetchone()
                
                result = safe_db_operation(check_task_status)
                
                if not result or result.status == 'cancelled':
                    self._log_warning("任务已被取消，停止执行")
                    return success_count, failed_count, 'cancelled'

                # 推送执行进度
                progress_msg = f'正在执行第 {i + 1}/{total_combinations} 个参数组合 {combination}'
                self._log_info(progress_msg)

                # 更新当前步数
                task.current_step = i + 1
                db_retry_manager.commit_with_retry(db.session)

                # 执行单个参数组合
                try:
                    success, result = self._execute_parameter_combination(combination, config_data)

                    if success:
                        success_count += 1
                        self._log_info(f'第 {i + 1} 个参数组合执行成功，{result}')
                    else:
                        self._log_warning(f'第 {i + 1} 个参数组合执行失败')
                        failed_count += 1
                        return success_count, failed_count, 'error'
                    combination.append(self.kline)
                    config_data['kline'] = self.kline
                    param_load = self._build_stock_param_result_payload(
                        task_name=name,
                        task_index=i,
                        config_data=config_data,
                        result=result,
                    )

                    # 保存结果到数据库
                    self._save_task_result(i, combination, result, success)
                    # 推送结果到 StockParamResult
                    self.send_stock_param_result_data(param_load)

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
                            self._log_info(f'第 {i + 1} 个参数组合执行中断（任务被取消）: {str(e)}')
                            break  # 退出循环
                    except:
                        pass

                    error_summary = self._record_execution_error_message(
                        e,
                        "execute_parameter_combination",
                    )
                    error_msg = f'第 {i + 1} 个参数组合执行出错: {error_summary}'
                    self._log_error(error_msg)
                    return success_count, failed_count, 'error'

                self._log_info(f"第 {i + 1} 个参数组合执行完成，成功: {success_count}, 失败: {failed_count}")

            self._log_info(f"批量数据处理完成，总成功: {success_count}, 总失败: {failed_count}")
            return success_count, failed_count, 'completed'
            
        except Exception as e:
            # 检查是否是任务被取消导致的异常
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
    @validate_result_dict(none_values=(None, '', ' ', '#N/A', '#DIV/0!', '#ERROR!', '#VALUE!', '#REF!', '#NAME?', '#NUM!'))
    def _execute_parameter_combination(self, combination: List, config_data: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """执行单个参数组合"""
        try:
            param_positions = config_data.get('parameter_positions', [])
            check_positions = config_data.get('check_positions', [])
            result_positions = config_data.get('result_positions', [])
            cell_updates, input_results = self._build_parameter_cell_updates(combination, param_positions)
            self._write_parameter_cells(cell_updates,config_data=config_data)

            sleep_num = 5
            batch_error_count = 0
            max_batch_error_count = 3
            for attempt in range(60):
                if attempt != 0 and (attempt % 10 == 0 or attempt in [3, 5, 8]):
                    self._log_info(f"第 {attempt + 1} 次检查执行状态前，刷新表格")
                    self._write_parameter_cells(cell_updates, attempt)

                config_manager = get_config_manager()
                delay_min = int(config_manager.get_config('execution_delay_min', 20))
                delay_max = int(config_manager.get_config('execution_delay_max', 30))
                if sleep_num <= 0:
                    sleep_num = 5
                delay = int(min(delay_min + sleep_num * 5, delay_max))
                sleep_num -= 1
                self._log_info(f"第 {attempt + 1} 次检查执行状态... delay {delay} 秒")
                if not self._interruptible_sleep(delay):
                    self._log_warning("task cancelled during wait")
                    raise RuntimeError("task cancelled")

                if self.google_sheet and check_positions:
                    try:
                        check_values = self.google_sheet.get_cells_batch(check_positions)
                        self._log_info(f"获取到检查位置的值: {check_values}")

                        if not self._validate_check_values(check_values, input_results):
                            self._log_info("检查位置验证失败，继续等待...")
                            continue
                    except Exception as err:
                        error_msg = f"批量检查位置时出错: {err}"
                        self._log_error(error_msg)
                        continue

                if self.google_sheet and result_positions:
                    try:
                        success, final_results = self._try_get_batch_results(
                            result_positions,
                            input_results,
                            config_data,
                        )
                        if not success:
                            continue

                        self._log_info(f"参数组合执行成功，结果: {final_results}")
                        return True, final_results

                    except checkForErrors:
                        raise
                    except Exception as err:
                        batch_error_count += 1
                        error_msg = f"批量获取结果时出错: {err}"
                        self._log_error(error_msg)

                        if batch_error_count <= max_batch_error_count:
                            continue

                        fallback_success, final_results = self._try_get_fallback_results(
                            result_positions,
                            input_results,
                            config_data,
                        )
                        if fallback_success:
                            self._log_info(f"参数组合执行成功，结果: {final_results}")
                            return True, final_results
                        return False, {}

            self._log_warning("执行超时，未在规定时间内完成")
            return False, {}

        except Exception as exc:
            record = record_task_exception(
                self.task_id,
                exc,
                "execute_parameter_combination",
                self.app,
                mark_error=False,
            )
            self._log_error(f"执行参数组合时出错: {format_task_error_message(record)}")
            raise

    def _save_task_result(self, step_index: int, parameters: List, result: Dict, success: bool):
        """保存任务结果到数据库，包含重试逻辑"""
        def save_result_operation():
            safe_parameters = self._sanitize_json_value(parameters)
            safe_result = self._sanitize_json_value(result)
            task_result = TaskResult(
                task_id=self.task_id,
                step_index=step_index,
                parameters=json.dumps(safe_parameters, allow_nan=False),
                result=json.dumps(safe_result, allow_nan=False),
                success=success
            )
            db.session.add(task_result)
            db.session.commit()
        
        try:
            if self.app:
                # 在后台线程中使用传递的应用实例
                with self.app.app_context():
                    safe_db_operation(save_result_operation)
            else:
                # 在主线程中使用当前应用上下文
                from flask import current_app
                with current_app.app_context():
                    safe_db_operation(save_result_operation)
        except Exception as e:
            error_msg = f"保存任务结果失败: {str(e)}"
            self._log_error(error_msg)
            # 注意：这里不能使用_push_log，因为可能导致循环调用

    def _get_parameter_combination_by_index(self, parameters: List[List], index: int) -> List:
        """
        根据索引按需计算参数组合，避免内存问题
        
        Args:
            parameters: 参数列表的列表
            index: 组合索引
            
        Returns:
            参数组合列表
        """
        try:
            logger.debug(f"计算第 {index} 个参数组合")
            combination = []
            remaining_index = index

            # 从最后一个参数开始计算
            for param_list in reversed(parameters):
                param_index = remaining_index % len(param_list)
                combination.insert(0, param_list[param_index])
                remaining_index = remaining_index // len(param_list)

            return combination
        except Exception as e:
            self._log_error(f"计算参数组合失败，索引: {index}, 错误: {str(e)}")
            raise
