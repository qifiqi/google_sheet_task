import json
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any

from flask import current_app
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.exceptions.checkForErrors import checkForErrors
from app.models import Task, TaskResult, db, TaskResultReturn
from app.services.google_sheet_service_base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation, db_retry_manager
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value
from app.services.xpl_service import xpl_analyzer
from app.utils.yf_api import YFApi
from app.utils.task_error_utils import build_task_error_message, unwrap_exception


class BacktestTrainingService(BaseGoogleSheetService):
    """回测数据服务 - backtest_training_service.py"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.xpl = xpl_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()

    def _task_detail_url(self) -> str:
        return f"{current_app.config.get('BASE_URL')}/backtest-training/detail/{self.task_id}"

    @staticmethod
    def _normalize_market_type(value):
        normalized = str(value or '').strip().lower()
        if normalized == 'cn':
            return 'cn'
        if normalized in ('en', 'us', 'usa'):
            return 'en'
        return 'cn'

    @alert_on_failure(
        result_predicate=should_alert_execute_task_result,
        message_builder=build_execute_task_alert,
    )
    def execute_task(self):
        """执行回测数据任务"""
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

    @staticmethod
    def _c3_to_c5_get_config(config_data):
        sheet = config_data.get('sheet')
        sheet_type = "C5" if "C5" in sheet.get('title','').upper() else "C3"
        if 'C5' in sheet_type.upper():
            input_column_d = config_data.get('c5_input_column_a').upper()
            input_column_v = config_data.get('c5_input_column_b').upper()
            output_range_1 = config_data.get('c5_output_range_1')
            output_range_2 = config_data.get('c5_output_range_2')
            output_column_index = config_data.get('c5_output_column_j')
            output_column_start = config_data.get('c5_output_column_l')
            parameter_positions = config_data.get('c5_parameter_positions')
            check_positions = config_data.get('c5_check_positions')
            last_row = "A"
        if 'C3' in sheet_type.upper():
            input_column_d = config_data.get('c3_input_column_d').upper()
            input_column_v = config_data.get('c3_input_column_e').upper()
            output_range_1 = config_data.get('c3_output_range_1')
            output_range_2 = config_data.get('c3_output_range_2')
            output_column_index = config_data.get('c3_output_column_K')
            output_column_start = config_data.get('c3_output_column_O')
            parameter_positions = config_data.get('c3_parameter_positions')
            check_positions = config_data.get('c3_check_positions')
            last_row = "D"
        return input_column_d, input_column_v, output_range_1, output_range_2, output_column_index, output_column_start, parameter_positions, check_positions,last_row

    def _resolve_resume_start_index(self, task):
        """Return the zero-based combination index to run next on checkpoint resume."""
        checkpoint_index = task.current_step - 1 if task.current_step >= 1 else 0
        if checkpoint_index < 0:
            checkpoint_index = 0

        saved_step_indexes = {
            row.step_index
            for row in TaskResult.query.with_entities(TaskResult.step_index)
            .filter_by(task_id=self.task_id)
            .all()
            if row.step_index is not None and row.step_index >= 0
        }
        if not saved_step_indexes:
            return checkpoint_index

        next_missing_index = 0
        while next_missing_index in saved_step_indexes:
            next_missing_index += 1

        return next_missing_index

    def get_bdl(self, task, name, parameters, config_data):
        """执行批量数据处理"""
        success_count = 0
        failed_count = 0
        try:
            input_column_d, input_column_v, output_range_1, output_range_2, output_column_index, output_column_start, parameter_positions, check_positions, last_row = self._c3_to_c5_get_config(config_data)
            full_years = config_data.get('full_years', [])
            recent_years = config_data.get('recent_years', [])
            parameters = config_data.get('parameters', [])
            stock_code = config_data.get('stock_code', '')
            market_type = self._normalize_market_type(
                config_data.get('market_type', 'cn')
            )

            total_combinations = 0
            precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应

            combinations, column_A_length,KLINE_DATA_MAP = self._get_all_parameters(
                full_years,
                recent_years,
                parameters,
                stock_code,
                market_type=market_type,
            )
            precomputed_params.append((combinations, column_A_length,KLINE_DATA_MAP))
            total_combinations += len(combinations)
            # 更新任务总步数
            task.total_steps = total_combinations
            db_retry_manager.commit_with_retry(db.session)

            # 推送参数组合信息
            self._log_info(f'将执行 {total_combinations} 个参数组合')

            # 检查是否从断点恢复（按组合级别）
            start_index = self._resolve_resume_start_index(task)
            self._log_info(f"任务将从第 {start_index + 1} 个参数组合开始执行")

            # 重置成功/失败计数器；如需精确恢复已完成组合数，可在外部通过历史结果统计
            success_count = start_index

            A_num = self.google_sheet.get_last_row(last_row)
            if A_num > 10:
                self._log_info(f'{self.google_sheet.title} 当前时间列行数: {A_num},准备滞空 时间列 值列')
                self.google_sheet.clear_range(f"{input_column_d}2:{input_column_v}{A_num+2}")

            self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
            if not self._interruptible_sleep(20):
                return success_count, failed_count, 'cancelled'

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
                        success, result = self._execute_parameter_combination(column_A_length, combination,cache_parameters, config_data,KLINE_DATA_MAP)

                        if success:
                            success_count += 1
                            self._log_info(f'第 {current_step} 个参数组合执行成功，{result}')
                        else:
                            self._log_warning(f'第 {current_step} 个参数组合执行失败')
                            failed_count += 1
                            return success_count, failed_count, 'error'

                        cache_parameters['combination'] = combination
                        kline = KLINE_DATA_MAP.get(combination['Kline_key'], None)
                        # 保存结果到数据库
                        self._save_task_result(current_step - 1, {
                            **combination,
                            'stock_code':combination['stock_code'],
                            'kline':[kline[0],kline[-1]],
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

                        error_msg = f'第 {current_step} 个参数组合执行出错: {str(e)}'
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

            error_msg = f"批量数据处理失败: {traceback.format_exc()}"
            self._log_error(error_msg)
            return 0, 1, 'error'

    @retry(
        stop=stop_after_attempt(3),  # 最多尝试3次
        wait=wait_exponential(multiplier=1, min=4, max=10),  # 指数退避：4s, 6s, 10s...
        reraise=True,  # 重试耗尽后重新抛出原始异常
        retry=retry_if_result(lambda result: result[0] is False)
    )
    def _execute_parameter_combination(self, column_A_length, combination,cache_parameters, config_data: Dict[str, Any],KLINE_DATA_MAP) -> tuple[
        bool, Dict[str, Any]]:
        """执行单个参数组合"""
        try:
            # 获取参数位置配置
            input_column_d, input_column_v, output_range_1, output_range_2, output_column_index, output_column_start, parameter_positions, check_positions, last_row = self._c3_to_c5_get_config(config_data)


            initial_results = {}
            results = {}
            cell_updates = {}
            parameter = combination['parameter']
            parameter[0] = str(parameter[0]).replace('"', '').replace("'","")
            parameter[1] = str(parameter[1]).replace('"', '').replace("'","")
            if len(parameter) == 2:
                c5_parameter_1 = f"xm:{parameter[0]}"
                c5_parameter_2 = f"ml:{parameter[1]}"
                cell_updates[parameter_positions[0]] = c5_parameter_1
                cell_updates[parameter_positions[1]] = c5_parameter_2
            else:
                for i, param in enumerate(parameter):
                    cell_updates[parameter_positions[i]] = param

            def set_googl_val(initial_result_sleep=None):
                Kline_key = combination['Kline_key']
                _combination = cache_parameters['combination']
                cache_Kline_key = _combination.get('Kline_key',"")
                kline = KLINE_DATA_MAP.get(Kline_key,None)
                _kline_len = len(kline)

                if Kline_key != cache_Kline_key or initial_result_sleep is not None:
                    # A_num = google_sheet.get_last_row('A')
                    A_num = column_A_length
                    self._log_info(f'{self.google_sheet.title} 当前A列行数: {A_num},预写入长度：{_kline_len} 准备滞空 A列 B列')
                    self.google_sheet.clear_range(f"{input_column_d}2:{input_column_v}{A_num+2}")
                    self._log_info(f'所有表格均滞空，等待20秒，开始执行后续逻辑')
                    if not self._interruptible_sleep(20):
                        raise RuntimeError("task cancelled")

                    # 准备要更新的单元格
                    for i in range(_kline_len):
                        item = {}
                        if i <= _kline_len:
                            item = kline[i]
                        cell_num = i + 2
                        cell_A = f"{input_column_d}{cell_num}"
                        cell_B = f"{input_column_v}{cell_num}"
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

                initial_results[self.google_sheet.spreadsheet_id] = self.google_sheet.get_range(output_range_1)

                self._log_info(f"向Google Sheet写入参数: {self.google_sheet.title} 长度：{len(cell_updates)}")
                self.google_sheet.update_jumped_cells(cell_updates)

            set_googl_val()
            Kline_key = combination['Kline_key']
            kline = KLINE_DATA_MAP.get(Kline_key, None)

            merged_return_range_a1 = f"{output_column_index}2:{output_column_start}{len(kline) + 1}"
            sleep_num = 5
            output_cell_list = [output_range_2,merged_return_range_a1] if len(parameter) == 2 else [merged_return_range_a1]

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

                # for position, value in check_values.items():
                #     if not value or value in ['#DIV/0!', '', '#N/A', '#ERROR!', '#VALUE!']:
                #         return False
                #     if 'target' in str(value).lower():
                #         return False

                _check_values = initial_results[spreadsheet_id]

                if (_check_values[check_positions[0]] == check_values[check_positions[0]]
                        and _check_values[check_positions[1]] == check_values[check_positions[1]]):
                    return False

                return True


            def get_sell_sleep(min_sleep: int, max_sleep: int) -> int:
                nonlocal sleep_num
                if sleep_num <= 0:
                    sleep_num = 5
                _ = min(min_sleep + sleep_num * 5, max_sleep)  # 最多60秒
                sleep_num -= 1
                return int(_)

            # 定时检查是否完成（最多检查60次，20-30秒）
            for attempt in range(60):
                # 定期刷新参数，防止模型卡顿
                if attempt != 0 and (attempt % 10 == 0 or attempt in [5,15,25,35]):
                    self._log_info(f"刷新参数")
                    set_googl_val(20)

                # 从配置获取执行延迟时间
                config_manager = get_config_manager()
                delay_min = int(config_manager.get_config('execution_delay_min', 20))
                delay_max = int(config_manager.get_config('execution_delay_max', 30))
                _ = get_sell_sleep(delay_min, delay_max)
                self._log_info(f"第 {attempt + 1} 次检查执行状态... delay {_} 秒")
                if not self._interruptible_sleep(_):
                    raise RuntimeError("task cancelled")
                all_num = 0
                _result = self.google_sheet.get_range(output_range_1)
                if _validate_check_values(_result, self.google_sheet.spreadsheet_id):
                    # _result = check_result(_result)
                    batch_range_values = self.google_sheet.get_ranges(output_cell_list)
                    _result_yearly = batch_range_values.get(output_range_2, {})
                    # _result_yearly = check_result(google_sheet.get_range(c5_output_range_2))
                    _result.update(_result_yearly)

                    try:
                        merged_return_range = batch_range_values.get(merged_return_range_a1, {})
                        _index_return = check_result({
                            position: value
                            for position, value in merged_return_range.items()
                            if position.startswith(output_column_index)
                        })
                        _start_return = check_result({
                            position: value
                            for position, value in merged_return_range.items()
                            if position.startswith(output_column_start)
                        })
                    except Exception as e:
                        self._log_info(f"获取结果位置 {output_column_index}2:{output_column_start}{len(kline) + 1} 时出错：{str(e)}")
                        self._log_info(f"_result：{_result} 起始参数:{initial_results[self.google_sheet.spreadsheet_id]}")
                        continue

                    _return_date = []
                    for i in range(len(kline)):
                        _return_date.append({
                            'date': kline[i].get('stock_date'),
                            'index_return': _index_return[f"{output_column_index}{i + 2}"],
                            'start_return': _start_return[f"{output_column_start}{i + 2}"]

                        })
                    calculate_metrics = self.xpl.get_calculate_metrics_v1(_return_date)
                    _result['calculate_metrics'] = calculate_metrics
                    results[f"{self.google_sheet.spreadsheet_id}__{self.google_sheet.title}"] = _result
                    return True, results
                else:
                    self._log_warning(f"第 {attempt + 1} 次检查执行状态... 未完成")
                    self._log_warning(f"第 {attempt + 1} 次检查执行状态... 结果:{_result} 起始参数:{initial_results[self.google_sheet.spreadsheet_id]}")
                    
            self._log_warning("执行超时，未在规定时间内完成")
            return False, {}

        except Exception as e:
            error_msg = f"执行参数组合时出错: {traceback.format_exc()}"
            self._log_error(error_msg)
            raise

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
            if _index_start_return_date:
                for i in _index_start_return_date:
                    task_result_return = TaskResultReturn(
                        task_id=self.task_id,
                        stock_date=i['stock_date'],
                        index_return=i['index_return'],
                        start_return=i['start_return']
                    )
                    db.session.add(task_result_return)
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

    def _get_all_parameters(
        self,
        full_years,
        recent_years,
        parameters,
        stock_code,price_mode="sp_price",market_type="cn"

    ):
        market_type = self._normalize_market_type(market_type)

        def _get_kline(klines, _year=None,_start_date_1=None, _end_date_1=None):
            # klines 里假设 'stock_date' 也是 'YYYY-MM-DD' 字符串
            # 根据price_mode决定使用开盘价还是收盘价
            price_field = 'stock_kp' if price_mode == 'kp_price' else 'stock_sp'
            
            if market_type == 'cn':
                if _year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                        for k in klines if int(k['stock_date'][:4]) == _year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                    for k in klines
                    if _start_date_1 <= k['stock_date'] <= _end_date_1
                ]
            else:
                if _year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                        for k in klines if int(k['stock_date'][:4]) == _year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k[price_field]}
                    for k in klines
                    if _start_date_1 <= k['stock_date'] <= _end_date_1
                ]


        end_dt = datetime.now() - timedelta(days=1)
        end_date = end_dt.strftime("%Y-%m-%d")

        if recent_years:
            year_count = max(int(year) for year in recent_years)
        elif full_years:
            earliest_full_year = min(int(year) for year in full_years)
            year_count = max(1, int(end_date[:4]) - earliest_full_year + 1)
        else:
            year_count = 1
        start_dt = end_dt - timedelta(days=365 * year_count)
        start_date = start_dt.strftime("%Y-%m-%d")

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

            klines = self.dfcf_api.get_stock_kline_data(stock_code, market, limit)
        else:
            klines = self.YF_api.get_kline_data(stock_code, '10y')

        # 获取K线数据的时间范围
        data_start_date = klines[0]['stock_date']
        data_end_date = klines[-1]['stock_date']

        if end_dt.weekday() >= 5:
            end_date = data_end_date

        # 检查用户设定的区间是否在数据范围内
        if start_date < data_start_date or end_date > data_end_date:
            raise Exception(
                f"股票{stock_code} 设定区间 [{start_date}, {end_date}] 不在K线数据范围 [{data_start_date}, {data_end_date}] 内")

        if len(klines) < 100:
            raise Exception(f"股票{stock_code} 数据量不足,k 线数据量小于100条，无法在模型正确产生数据，或者联系开发")

        all_kline = _get_kline(klines, _start_date_1=start_date, _end_date_1=end_date)
        data = []

        KLINE_DATA_MAP = {}

        if recent_years:
            for year in recent_years:

                _end_data = end_date
                _start_data = f"{int(end_date[:4]) - year}{end_date[4:]}"
                kline = _get_kline(klines, _start_date_1=_start_data, _end_date_1=_end_data)
                Kline_key = f'{_end_data[:4]}-{_start_data[:4]}'
                for item in parameters:
                    d = {"parameter": item, 'stock_code': stock_code, 'year': Kline_key,'Kline_key':Kline_key}
                    if kline:
                        if Kline_key not in KLINE_DATA_MAP:
                            KLINE_DATA_MAP[Kline_key] = kline
                    data.append(d)

        if full_years:
            _all_kline = [k for k in klines if start_date <= k['stock_date'] <= end_date]
            for year in full_years:
                kline = _get_kline(_all_kline, _year=year)
                Kline_key = year

                for item in parameters:
                    d = {"parameter": item,  'stock_code': stock_code, 'year': year,'Kline_key':Kline_key}
                    if kline:
                        if Kline_key not in KLINE_DATA_MAP:
                            KLINE_DATA_MAP[Kline_key] = kline

                    data.append(d)

        return data, len(all_kline) + 20,KLINE_DATA_MAP

