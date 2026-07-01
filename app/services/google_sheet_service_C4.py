import json
import time
import traceback
from typing import Dict, Any

from flask import current_app
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.exceptions.checkForErrors import checkForErrors
from app.models import Task, TaskResult, db
from app.services.google_sheet_service_base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation, db_retry_manager
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import validate_result_dict, is_valid_result_value
from app.services.xpl_service import xpl_analyzer
from app.utils.yf_api import YFApi
from app.utils.task_error_utils import build_task_error_message, unwrap_exception
from app.utils.kline_validation import require_kline_rows


class GoogleSheetService(BaseGoogleSheetService):
    """Google Sheet服务 - C4"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.google_sheets: list[GoogleSheet] = []
        self.xpl = xpl_analyzer

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
                # 尝试获取 Postgres Advisory Lock，防止并发执行同一任务
                lock_acquired = False
                try:
                    lock_acquired = db.session.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": int(self.task_id)}
                    ).scalar()
                    if not lock_acquired:
                        self._log_warning(f"任务 {self.task_id} 已在运行（获取锁失败），拒绝并发执行 (C4)")
                        return 'already_running'
                except Exception:
                    # 非 Postgres 或锁不可用时忽略，继续执行（由上层状态原子更新兜底）
                    pass
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
            if self.task:
                self.task.error_message = build_task_error_message(e)
                db.session.commit()
            error_msg = f"执行Google Sheet任务失败: {self.task_id}, 错误: {str(root)}"
            self._log_error(error_msg)
            return 'error'
        finally:
            # 释放 Advisory Lock（仅当成功获取时）
            try:
                if 'lock_acquired' in locals() and lock_acquired:
                    db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(self.task_id)})
            except Exception:
                pass

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
                "kline_range": combination.get("year", ""),
            },
        )
        model_result = result
        if isinstance(result, dict):
            first_value = next(iter(result.values()), None)
            if isinstance(first_value, dict):
                model_result = first_value
        analyze_result = (
            model_result.get("flat_result")
            if isinstance(model_result.get("flat_result"), dict)
            else model_result
        )
        payload.update({
            "return_rate": model_result.get("D2", 0),
            "annualized_rate": model_result.get("D3", 0),
            "maxdd": model_result.get("D4", 0),
            "index_rate": model_result.get("D5", 0),
            "index_annualized_rate": model_result.get("D6", 0),
            "max_index_dd": model_result.get("D7", 0),
            "fee_total": model_result.get("D8", 0),
            "fee_annualized": model_result.get("D9", 0),
            "turnover_rate": model_result.get("D10", 0),
            "return_beats": model_result.get("D11", 0),
            "dd_beats": model_result.get("D12", 0),
            "max_1y_beats": model_result.get("D13", 0),
            "min_1y_beats": model_result.get("D14", 0),
            "max_theoretical_leverage": model_result.get("D15", 0),
            "avg_theoretical_leverage": model_result.get("D16", 0),
            "unit_theoretical_leverage_return": model_result.get("D17", 0),
            "max_actual_leverage": model_result.get("D18", 0),
            "avg_actual_leverage": model_result.get("D19", 0),
            "unit_actual_leverage_return": model_result.get("D20", 0),
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
            "index_sotino_ratio": analyze_result.get("index_sotino_ratio", 0),
            "start_sotino_ratio": analyze_result.get("start_sotino_ratio", 0),
            "excess_sharp": analyze_result.get("excess_sharp", 0),
            "excess_of_promissory_note": analyze_result.get("excess_of_promissory_note", 0),
        })
        return payload

    def get_bdl(self, task, name, parameters, config_data):
        """执行批量数据处理"""
        success_count = 0
        failed_count = 0
        try:
            # 计算总参数组合数（按每个具体组合计数）
            count_mode = config_data.get('count_mode', 'n_plus_1')
            date_range_mode = config_data.get('date_range_mode',[])
            end_date = config_data.get('end_date')
            start_date = config_data.get('start_date')
            market_type = config_data.get('market_type')
            adjust_type = config_data.get('kline_adjustment')
            c4_input_column_a = config_data.get('c4_input_column_a').upper()
            c4_input_column_b = config_data.get('c4_input_column_b').upper()

            # 仅使用 parameters[0] 作为外层参数列表，真实总组合数为所有 inner combinations 数量之和
            total_combinations = 0
            precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应
            for outer_param in parameters[0]:
                combinations, column_A_length = self._get_all_parameters(
                    outer_param, count_mode, end_date, start_date, market_type,date_range_mode, adjust_type
                )
                precomputed_params.append((combinations, column_A_length))
                total_combinations += len(combinations)

            # 更新任务总步数
            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

            # 推送参数组合信息
            self._log_info(f'将执行 {total_combinations} 个参数组合')

            # 检查是否从断点恢复（按组合级别）
            start_index = task.current_step - 1 if task.current_step >= 1 else 0
            if start_index < 0:
                start_index = 0
            self._log_info(f"任务将从第 {start_index + 1} 个参数组合开始执行")

            # 重置成功/失败计数器；如需精确恢复已完成组合数，可在外部通过历史结果统计
            success_count = start_index

            for google_sheet in self.google_sheets:
                A_num = google_sheet.get_last_row('A')
                if A_num < 10:
                    continue
                self._log_info(f'{google_sheet.title} 当前A列行数: {A_num},准备滞空 A列 B列')
                google_sheet.clear_range(f"{c4_input_column_a}2:{c4_input_column_b}{A_num+2}")

            self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
            if not self._interruptible_sleep(20):
                return success_count, failed_count, 'cancelled'

            processed_index = 0  # 已处理的组合数量

            for outer_idx, (combinations, column_A_length) in enumerate(precomputed_params):

                for combination in combinations:
                    if self._is_cancel_requested():
                        return success_count, failed_count, 'cancelled'
                    # 跳过已完成的组合（断点恢复）
                    if processed_index < start_index:
                        processed_index += 1
                        continue

                    # 原子性检查任务是否被取消（每个外层参数进入前检查一次）
                    def check_task_status():
                        return db.session.execute(
                            text("SELECT status FROM tasks WHERE id = :task_id"),
                            {"task_id": self.task_id}
                        ).fetchone()

                    result = safe_db_operation(check_task_status)

                    if not result or result.status == 'cancelled':
                        self._log_warning("任务已被取消，停止执行")
                        return success_count, failed_count, 'cancelled'

                    current_step = processed_index + 1

                    self._log_step(current_step, total_combinations, f"开始执行参数组合")

                    # 推送执行进度
                    progress_msg = f'正在执行第 {current_step}/{total_combinations} 个参数组合'
                    self._log_info(progress_msg)

                    # 更新当前步数为组合级别
                    task.current_step = current_step
                    db_retry_manager.commit_with_retry(db.session)

                    # 执行单个参数组合
                    try:
                        success, result = self._execute_parameter_combination(column_A_length, combination, config_data)

                        if success:
                            success_count += 1
                            self._log_info(f'第 {current_step} 个参数组合执行成功，{result}')
                        else:
                            self._log_warning(f'第 {current_step} 个参数组合执行失败')
                            failed_count += 1
                            return success_count, failed_count, 'error'

                        # 保存结果到数据库
                        self._save_task_result(current_step - 1, {
                            'stock_code':combination['stock_code'],
                            'kline':[combination['kline'][0],combination['kline'][-1]]
                        }, result, success)
                        self.send_stock_param_result_data(
                            self._build_stock_param_result_payload(
                                name,
                                current_step - 1,
                                combination,
                                result,
                            )
                        )

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

                        error_summary = self._record_execution_error_message(e)
                        error_msg = f'第 {current_step} 个参数组合执行出错: {error_summary}'
                        self._log_error(error_msg)
                        return success_count, failed_count, 'error'

                    processed_index += 1

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

            error_msg = f"批量数据处理失败: {traceback.format_exc()}"
            self._log_error(error_msg)
            return 0, 1, 'error'

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool):
        """保存任务结果到数据库，包含重试逻辑"""

        def save_result_operation():
            _index_start_return_date = None
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
                with self.app.app_context():
                    safe_db_operation(save_result_operation)
            else:
                from flask import current_app
                with current_app.app_context():
                    safe_db_operation(save_result_operation)
        except Exception as e:
            error_msg = f"保存任务结果失败: {str(e)}"
            self._log_error(error_msg)



    @retry(
        stop=stop_after_attempt(3),  # 最多尝试3次
        wait=wait_exponential(multiplier=1, min=4, max=10),  # 指数退避：4s, 6s, 10s...
        reraise=True,  # 重试耗尽后重新抛出原始异常
        retry=retry_if_result(lambda result: result[0] is False)
    )
    @validate_result_dict(
        none_values=(None, '', ' ', '#N/A', '#DIV/0!', '#ERROR!', '#VALUE!', '#REF!', '#NAME?', '#NUM!'))
    def _execute_parameter_combination(self, column_A_length, combination, config_data: Dict[str, Any]) -> tuple[
        bool, Dict[str, Any]]:
        """执行单个参数组合"""
        try:
            # 获取参数位置配置
            c4_input_column_a = config_data.get('c4_input_column_a').upper()
            c4_input_column_b = config_data.get('c4_input_column_b').upper()

            c4_output_range_1 = config_data.get('c4_output_range_1')
            c4_output_range_2 = config_data.get('c4_output_range_2')
            c4_output_column_j = config_data.get('c4_output_column_j')
            c4_output_column_l = config_data.get('c4_output_column_l')

            for google_sheet in self.google_sheets:
                # A_num = google_sheet.get_last_row('A')
                A_num = column_A_length
                self._log_info(f'{google_sheet.title} 当前A列行数: {A_num},准备滞空 A列 B列')
                google_sheet.clear_range(f"{c4_input_column_a}2:{c4_input_column_b}{A_num+2}")

            initial_results = {}

            results = {}

            cell_updates = {}

            kline = combination['kline']
            # 准备要更新的单元格
            for i in range(len(kline)):
                item = {}
                if i <= len(kline):
                    item = kline[i]
                cell_num = i + 2
                cell_A = f"{c4_input_column_a}{cell_num}"
                cell_B = f"{c4_input_column_b}{cell_num}"
                stock_date = item.get('stock_date', "")
                stock_val = item.get('stock_val', "")
                cell_updates[cell_A] = stock_date
                cell_updates[cell_B] = stock_val

            for google_sheet in self.google_sheets:
                self._log_info(f"向Google Sheet写入参数: {google_sheet.title} 长度：{len(cell_updates)}")
                google_sheet.update_jumped_cells(cell_updates)
                initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c4_output_range_1)

            def check_result(check_values):
                _check_values = {}
                for _position, _value in check_values.items():
                    if not _value or not is_valid_result_value(_value):
                        self._log_info(f"结果位置 {_position} 值为空或无效，跳过重新检查")
                        raise Exception(f"结果位置 {_position} 值为空或无效，跳过重新检查")

                    if str(_value).strip().startswith(("#", "#N/A")):
                        _error_msg = f"获取结果位置 {_position} 时出错: {str(_value)}"
                        raise checkForErrors(f"检查报错，出现#|#N/A 这种异常错误，联系用户检查 {_error_msg}")

                    if '%' in _value:
                        _value = float(_value.replace('%', '').replace(',', '')) / 100
                    if isinstance(_value, str):
                        _value = float(_value.replace(',', ''))
                    _check_values[_position] = _value
                return _check_values

            def _validate_check_values(check_values: Dict[str, Any], spreadsheet_id) -> bool:
                """验证检查位置的值是否有效"""
                if not check_values:
                    return False

                for position, value in check_values.items():
                    if not value or value in ['#DIV/0!', '', '#N/A', '#ERROR!', '#VALUE!']:
                        return False
                    if 'target' in str(value).lower():
                        return False

                _check_values = initial_results[spreadsheet_id]

                if _check_values['D2'] == check_values['D2'] and _check_values['D3'] == check_values['D3']:
                    return False

                return True

            sleep_num = 5

            def get_sell_sleep(min_sleep: int, max_sleep: int) -> int:
                nonlocal sleep_num
                if sleep_num <= 0:
                    sleep_num = 5
                _ = min(min_sleep + sleep_num * 5, max_sleep)  # 最多60秒
                sleep_num -= 1
                return int(_)

            # 定时检查是否完成（最多检查60次，20-30秒）
            for attempt in range(60):
                # 从配置获取执行延迟时间
                config_manager = get_config_manager()
                delay_min = int(config_manager.get_config('execution_delay_min', 20))
                delay_max = int(config_manager.get_config('execution_delay_max', 30))
                _ = get_sell_sleep(delay_min, delay_max)
                self._log_info(f"第 {attempt + 1} 次检查执行状态... delay {_} 秒")
                if not self._interruptible_sleep(_):
                    raise RuntimeError("task cancelled")
                all_num = 0
                for google_sheet in self.google_sheets:
                    self._log_info(f"向Google Sheet写入参数: {google_sheet.title}")
                    _result = google_sheet.get_range(c4_output_range_1)
                    if _validate_check_values(_result, google_sheet.spreadsheet_id):
                        # _result = check_result(_result)
                        _result_yearly = google_sheet.get_range(c4_output_range_2)
                        # _result_yearly = check_result(google_sheet.get_range(c4_output_range_2))
                        _index_return = check_result(
                            google_sheet.get_range(f"{c4_output_column_j}2:{c4_output_column_j}{len(kline) + 1}")
                        )
                        _start_return = check_result(
                            google_sheet.get_range(f"{c4_output_column_l}2:{c4_output_column_l}{len(kline) + 1}")
                        )
                        _index_return_date = []
                        _start_return_date = []
                        _return_data = []
                        for i in range(len(kline)):
                            # _index_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _index_return[f"{c4_output_column_j}{i + 2}"]
                            # })
                            # _start_return_date.append({
                            #     'stock_date': kline[i].get('stock_date'),
                            #     'stock_val': _start_return[f"{c4_output_column_l}{i + 2}"]
                            # })
                            _return_data.append({
                                'date': kline[i].get('stock_date'),
                                'index_return': _index_return[f"{c4_output_column_j}{i + 2}"],
                                'start_return': _start_return[f"{c4_output_column_l}{i + 2}"],
                            })

                        # _index_return_xpl = self.xpl.get_xpl(_index_return_date,'stock_date','stock_val')
                        # _start_return_xpl = self.xpl.get_xpl(_start_return_date,'stock_date','stock_val')
                        flat_result, analyze_result = self.xpl.get_return_analysis_v1(_return_data)
                        _result.update(_result_yearly)
                        # _result['index_return_xpl'] = _index_return_xpl
                        # _result['start_return_xpl'] = _start_return_xpl
                        _result['analyze_result'] = analyze_result
                        _result['flat_result'] = flat_result
                        results[f"{google_sheet.spreadsheet_id}__{google_sheet.title}"] = _result
                        all_num += 1
                    else:
                        self._log_warning(f"第 {attempt + 1} 次检查执行状态... 未完成")
                        self._log_warning(f"第 {attempt + 1} 次检查执行状态... 结果:{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                        break

                if all_num == len(self.google_sheets):
                    self._log_info(f"所有任务已完成")
                    return True, results

                if attempt in [5,15,25,35]:
                    for google_sheet in self.google_sheets:
                        self._log_info(f"向Google Sheet写入参数: {google_sheet.title}")
                        google_sheet.update_jumped_cells(cell_updates)

                    if not self._interruptible_sleep(30):
                        raise RuntimeError("task cancelled")
                    for google_sheet in self.google_sheets:
                        self._log_info(f"向Google Sheet写入参数: {google_sheet.title}")
                        initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c4_output_range_1)

            self._log_warning("执行超时，未在规定时间内完成")
            return False, {}

        except Exception as e:
            error_msg = f"执行参数组合时出错: {traceback.format_exc()}"
            self._log_error(error_msg)
            raise

    @staticmethod
    def _get_all_parameters(parameter, count_mode, end_date, start_date, market_type,date_range_mode, adjust_type=None):

        def _get_kline(klines, year=None,_start_date=None, _end_date=None):
            # klines 里假设 'stock_date' 也是 'YYYY-MM-DD' 字符串
            price_field = 'stock_kp' if market_type == 'cn' else 'stock_sp'
            if market_type == 'cn':
                if year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                        for k in klines if int(k['stock_date'][:4]) == year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                    for k in klines
                    if _start_date <= k['stock_date'] <= _end_date
                ]
            else:
                if year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                        for k in klines if int(k['stock_date'][:4]) == year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                    for k in klines
                    if _start_date <= k['stock_date'] <= _end_date
                ]



        if market_type == 'cn':
            dfcf_api = DFCJStockApi()
            stock_config = dfcf_api.get_search_list_by_stock_code(parameter, 10)
            stock_config = [i for i in stock_config if 'A' in  i['securityTypeName']]
            if stock_config:
                stock_config = stock_config[0]
            market = stock_config['market']
        else:
            yf_api = YFApi()

        _end_year_1 = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        _end_year = int(now_time[:4])
        _start_date = int(start_date[:4])
        limit = (_end_year - _start_date + 1) * 250
        if market_type == 'cn':
            klines = dfcf_api.get_stock_kline_data(parameter, market, limit, adjust_type=adjust_type)
        else:
            klines = yf_api.get_kline_data(parameter, '10y', adjust_type=adjust_type)
        klines = require_kline_rows(
            parameter,
            market_type,
            klines,
            context="原始K线",
            min_rows=30,
            price_field='stock_kp' if market_type == 'cn' else 'stock_sp',
        )
        data_start_date = klines[0]['stock_date']
        data_end_date = klines[-1]['stock_date']
        if end_date > data_end_date:
            raise ValueError(
                f"股票{parameter} 设定区间 [{start_date}, {end_date}] 不在K线数据范围 [{data_start_date}, {data_end_date}] 内"
            )
        all_kline = _get_kline(klines, _start_date=start_date, _end_date=end_date)
        all_kline = require_kline_rows(
            parameter,
            market_type,
            all_kline,
            context="写入Sheet K线",
            start_date=start_date,
            end_date=end_date,
            latest_date=data_end_date,
        )
        data = [
            {'stock_code': parameter, 'kline': all_kline}
        ]

        if count_mode != 'n_plus_1':
            return data,len(all_kline) + 20

        if 'recent' in date_range_mode:
            if count_mode == 'n_plus_1':
                for i in range(1, (_end_year_1 - _start_date) + 1):
                    _i = i
                    if i!=0:
                        _i = i - 1

                    _end_data = f"{_end_year_1-_i}{end_date[4:]}"
                    _start_data = f"{_end_year_1 - i}{end_date[4:]}"
                    d = {}
                    kline = _get_kline(klines, _start_data, _end_data)
                    if kline:
                        d['stock_code'] = parameter
                        d['kline'] = kline

                        data.append(d)

        if 'full' in date_range_mode:
            all_kline = [ k for k in klines if start_date <= k['stock_date'] <= end_date]
            for i in range(_start_date, _end_year_1 + 1):
                d = {}
                kline = _get_kline(all_kline,year=i)
                if kline and len(kline) > 30:
                    d['stock_code'] = parameter
                    d['year'] = i
                    d['kline'] = kline

                    data.append(d)

        return data, len(all_kline) + 20


if __name__ == '__main__':
    GoogleSheetService({}, '')._get_all_parameters('000001', 'n_plus_1', '2025-05-01', '2023-05-01', 'cn')
