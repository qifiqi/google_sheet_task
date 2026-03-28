import json
import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from flask import current_app
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.exceptions.checkForErrors import checkForErrors
from app.models import Task, TaskResult, db
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.db_retry import safe_db_operation, db_retry_manager
from app.utils.db_stock_api import StockAPIClient
from app.utils.dfcf_api import DFCJStockApi
from app.utils.logger import get_logger
from app.utils.result_validator import validate_result_dict, is_valid_result_value
from app.services.xpl_service import xpl_analyzer
logger = get_logger(__name__)


class GoogleSheetService:
    """Google Sheet服务"""

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None, stop_event=None):
        self.config = config
        self.google_sheets: list[GoogleSheet] = []
        self.api_client = StockAPIClient()
        # 保存参数到实例变量
        self.task_id = task_id
        self.event_queue = event_queue
        self.app = app
        self.stop_event = stop_event
        self.task_name = ''
        # 创建任务专用日志记录器 - 不使用TaskLogger的前缀功能，我们自己控制格式
        self.task_logger = get_logger(f"{__name__}.{task_id}")
        self.xpl = xpl_analyzer

    def _is_cancel_requested(self) -> bool:
        if self.stop_event and self.stop_event.is_set():
            return True
        try:
            task = Task.query.get(self.task_id)
            return bool(task and task.status == 'cancelled')
        except Exception:
            return False

    def _interruptible_sleep(self, seconds: float) -> bool:
        if seconds <= 0:
            return not self._is_cancel_requested()
        if self.stop_event:
            return not self.stop_event.wait(seconds)
        time.sleep(seconds)
        return not self._is_cancel_requested()

    def _task_display_name(self) -> str:
        return self.task_name or self.task_id

    def error_dd(self, error_msg):
        error_msg = self.app.notifier.error_google_task_templates(
            f"{self.task_id} -- {self._task_display_name()}",
            error_msg,
            f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}")
        self.app.notifier.send_message(error_msg)

    def task_ok_to_dd(self, result):
        error_msg = self.app.notifier.google_task_ok_templates(
            f"{self.task_id} -- {self._task_display_name()}",
            result,
            f"{current_app.config.get('BASE_URL')}/google-sheet/detail?task_id={self.task_id}"
        )
        self.app.notifier.send_message(error_msg)

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
                task = Task.query.get(self.task_id)
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
                    # 任务执行出错
                    # 推送错误通知
                    error_details = f'任务执行出错！成功: {success_count}, 失败: {failed_count}'
                    if task.error:
                        error_details += f', 错误信息: {str(task.error)}'
                    self.error_dd(error_details)
                    return 'error'

                if success_count == 0 and failed_count == 0:
                    self._log_error('任务执行失败')
                    # 推送无结果失败通知
                    self.error_dd('任务执行失败！没有成功或失败的参数组合')
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
                task = Task.query.get(self.task_id)
                if task and task.status == 'cancelled':
                    self._log_info(f'任务已被取消: {str(e)}')
                    return 'cancelled'
            except:
                pass

            # 其他异常情况
            error_msg = f"执行Google Sheet任务失败: {self.task_id}, 错误: {str(e)}"
            self._log_error(error_msg)
            self.error_dd(error_msg)
            return 'error'
        finally:
            # 释放 Advisory Lock（仅当成功获取时）
            try:
                if 'lock_acquired' in locals() and lock_acquired:
                    db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(self.task_id)})
            except Exception:
                pass

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
            c4_input_column_a = config_data.get('c4_input_column_a').upper()
            c4_input_column_b = config_data.get('c4_input_column_b').upper()

            # 仅使用 parameters[0] 作为外层参数列表，真实总组合数为所有 inner combinations 数量之和
            total_combinations = 0
            precomputed_params = []  # [(combinations, column_A_length)] 与 parameters[0] 对应
            for outer_param in parameters[0]:
                combinations, column_A_length = self._get_all_parameters(
                    outer_param, count_mode, end_date, start_date, market_type,date_range_mode
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

                    except checkForErrors as e:
                        self._log_error(str(e))
                        task.error = e
                        return success_count, failed_count, 'error'
                    except Exception as e:
                        failed_count += 1
                        # 检查是否是任务被取消
                        task.error = e
                        try:
                            task_check = Task.query.get(self.task_id)
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
            try:
                task_check = Task.query.get(self.task_id)
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
        reraise=True  # 重试耗尽后重新抛出原始异常
    )
    def send_stock_template_param_data(self, payload: Dict, log) -> int:
        """
        发送股票模板参数数据

        Args:
            payload: 参数数据字典

        Returns:
            返回的ID或0
        """
        try:
            self._log_api("发送股票模板参数数据", f"payload: {payload}")
            result = self.api_client.insert_stock_template_param(payload)
            self._log_api("发送股票模板参数数据成功", f"ID: {result}")
            return result
        except Exception as e:
            self._log_api_error("发送股票模板参数数据", str(e))
            log('error', f"发送股票模板参数数据失败: {str(e)}")
            raise e

    @retry(
        stop=stop_after_attempt(3),  # 最多尝试3次
        wait=wait_exponential(multiplier=1, min=4, max=10),  # 指数退避：4s, 6s, 10s...
        reraise=True  # 重试耗尽后重新抛出原始异常
    )
    def get_single_stock_template_param(self, stock_no: str) -> Optional[Dict]:
        """
        获取单个股票模板参数
        
        Args:
            stock_no: 股票编号
            
        Returns:
            股票参数字典或None
        """
        try:
            self._log_api("获取股票模板参数", f"stock_no: {stock_no}")
            result = self.api_client.get_single_stock_template_param(stock_no)
            self._log_api("获取股票模板参数成功", f"返回结果: {type(result)}")
            return result
        except Exception as e:
            self._log_api_error("获取股票模板参数", str(e))
            raise

    def _init_google_sheet(self, config_data: Dict[str, Any]):
        """初始化Google Sheet连接"""
        try:
            self._log_info("开始初始化Google Sheet连接")

            sheets = config_data.get('sheets')

            token_file = config_data.get('token_file', 'data/token.json')
            proxy_url = config_data.get('proxy_url', None)

            if not sheets:
                error_msg = "缺少spreadsheet_id配置"
                self._log_error(error_msg)
                raise ValueError(error_msg)
            self._log_info(f"连接参数 - sheets: {sheets},Token: {token_file}")
            if proxy_url:
                self._log_info(f"使用代理: {proxy_url}")
            for sheet in sheets:
                spreadsheet_id = sheet.get('spreadsheet_id')
                sheet_name = sheet.get('sheet_name', 'data')
                google_sheet = GoogleSheet(spreadsheet_id, sheet_name, token_file, proxy_url, task_id=self.task_id)
                if not google_sheet.worksheet:
                    raise Exception("请先选择工作表")
                self.google_sheets.append(google_sheet)
                self._log_info(f"已连接工作表: {sheet}")

        except Exception as e:
            error_msg = f"初始化Google Sheet连接失败: {str(e)}"
            self._log_error(error_msg)
            raise

    @staticmethod
    def get_worksheets(spreadsheet_id: str, token_file: str = "data/token.json", proxy_url: str = None) -> Dict[
        str, Any]:
        """
        获取指定电子表格的基础信息

        Args:
            spreadsheet_id: 电子表格ID
            token_file: 认证文件路径
            proxy_url: 代理URL

        Returns:
            {
                "title": 表格标题（spreadsheet 的名称）, 
                "worksheets": 工作表名称列表
            }
        """
        try:
            # 使用上下文管理器确保连接被正确关闭
            with GoogleSheet(spreadsheet_id, None, token_file, proxy_url) as google_sheet:
                # 获取所有工作表名称
                worksheets = google_sheet.get_all_worksheets()
                if not worksheets:
                    raise ValueError("未找到任何工作表")

                title = google_sheet.sheet.title if google_sheet.sheet else ""
                return {"title": title, "worksheets": worksheets}
        except Exception as e:
            logger.error(f"获取工作表列表失败: {str(e)}")
            raise

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
                        for i in range(len(kline)):
                            _index_return_date.append({
                                'stock_date': kline[i].get('stock_date'),
                                'stock_val': _index_return[f"{c4_output_column_j}{i + 2}"]
                            })
                            _start_return_date.append({
                                'stock_date': kline[i].get('stock_date'),
                                'stock_val': _start_return[f"{c4_output_column_l}{i + 2}"]
                            })

                        _index_return_xpl = self.xpl.get_xpl(_index_return_date,'stock_date','stock_val')
                        _start_return_xpl = self.xpl.get_xpl(_start_return_date,'stock_date','stock_val')
                        _result.update(_result_yearly)
                        _result['index_return_xpl'] = _index_return_xpl
                        _result['start_return_xpl'] = _start_return_xpl
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
            raise e

    def _log(self, level: str, message: str, log_type: str = 'general', **kwargs):
        """
        统一的日志记录接口 - 完整版，包含前端推送和数据库保存
        
        Args:
            level: 日志级别 ('info', 'warning', 'error')
            message: 日志消息
            log_type: 日志类型 ('general', 'step', 'progress', 'api', 'api_error')
            **kwargs: 额外参数，用于特定类型的日志
        """
        try:
            # 根据日志类型格式化消息
            formatted_message = self._format_log_message(message, log_type, **kwargs)

            # 添加简洁的任务ID前缀
            prefixed_message = f"[Task-{self.task_id[:8]}] {formatted_message}"

            # 1. 记录到系统日志（现在已经不会重复了）
            if level == 'error':
                self.task_logger.error(prefixed_message)
            elif level == 'warning':
                self.task_logger.warning(prefixed_message)
            else:
                self.task_logger.info(prefixed_message)

            # 2. 保存到数据库（TaskLog）
            self._save_to_database(level, formatted_message)

            # 3. 推送到前端（SSE）
            self._push_to_frontend(level, formatted_message)

        except Exception as e:
            # 记录日志系统本身的错误，但不引起循环
            pass

    def _format_log_message(self, message: str, log_type: str, **kwargs) -> str:
        """格式化日志消息"""
        if log_type == 'step':
            step = kwargs.get('step', 0)
            total = kwargs.get('total', 0)
            return f"[Step {step}/{total}] {message}"
        elif log_type == 'progress':
            percentage = kwargs.get('percentage', 0)
            return f"[Progress {percentage:.1f}%] {message}"
        elif log_type == 'api':
            action = kwargs.get('action', '')
            details = kwargs.get('details', '')
            base_msg = f"[API] {action}"
            return f"{base_msg} - {details}" if details else base_msg
        elif log_type == 'api_error':
            action = kwargs.get('action', '')
            error = kwargs.get('error', '')
            return f"[API_ERROR] {action} - {error}"
        else:
            return message

    def _save_to_database(self, level: str, message: str):
        """保存日志到数据库，包含重试逻辑"""
        from app.models import TaskLog
        from app.utils.database import safe_db_operation
        from flask import current_app

        def save_log_operation():
            log = TaskLog(
                task_id=self.task_id,
                level=level,
                message=message
            )
            db.session.add(log)
            db.session.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_log_operation)
            else:
                with current_app.app_context():
                    safe_db_operation(save_log_operation)
        except Exception as e:
            # 数据库保存失败时静默处理，不影响主流程
            pass

    def _push_to_frontend(self, level: str, message: str):
        """推送日志到前端"""
        try:
            if self.event_queue:
                self.event_queue.put({
                    "type": "log_update",
                    "data": {
                        "level": level,
                        "message": message,
                        "timestamp": datetime.now().isoformat()
                    }
                })
        except Exception as e:
            # 前端推送失败时静默处理，不影响主流程
            pass

    # 便捷的日志方法
    def _log_info(self, message: str, log_type: str = 'general', **kwargs):
        """记录info级别日志"""
        self._log('info', message, log_type, **kwargs)

    def _log_warning(self, message: str, log_type: str = 'general', **kwargs):
        """记录warning级别日志"""
        self._log('warning', message, log_type, **kwargs)

    def _log_error(self, message: str, log_type: str = 'general', **kwargs):
        """记录error级别日志"""
        self._log('error', message, log_type, **kwargs)

    def _log_step(self, step: int, total: int, message: str):
        """记录步骤日志"""
        self._log('info', message, 'step', step=step, total=total)

    def _log_progress(self, percentage: float, message: str):
        """记录进度日志"""
        self._log('info', message, 'progress', percentage=percentage)

    def _log_api(self, action: str, details: str = ''):
        """记录API调用日志"""
        self._log('info', '', 'api', action=action, details=details)

    def _log_api_error(self, action: str, error: str):
        """记录API错误日志"""
        self._log('error', '', 'api_error', action=action, error=error)

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool):
        """保存任务结果到数据库，包含重试逻辑"""

        def save_result_operation():
            task_result = TaskResult(
                task_id=self.task_id,
                step_index=step_index,
                parameters=json.dumps(parameters),
                result=json.dumps(result),
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

    @staticmethod
    def _get_all_parameters(parameter, count_mode, end_date, start_date, market_type,date_range_mode):

        def _get_kline(klines, year=None,_start_date=None, _end_date=None):
            # klines 里假设 'stock_date' 也是 'YYYY-MM-DD' 字符串
            if market_type == 'cn':
                if year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k['stock_kp']}
                        for k in klines if int(k['stock_date'][:4]) == year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k['stock_kp']}
                    for k in klines
                    if _start_date <= k['stock_date'] <= _end_date
                ]
            else:
                if year:
                    return [
                        {'stock_date': k['stock_date'], 'stock_val': k['stock_sp']}
                        for k in klines if int(k['stock_date'][:4]) == year
                    ]
                return [
                    {'stock_date': k['stock_date'], 'stock_val': k['stock_sp']}
                    for k in klines
                    if _start_date <= k['stock_date'] <= _end_date
                ]



        dfcf_api = DFCJStockApi()
        stock_config = dfcf_api.get_search_list_by_stock_code(parameter, 10)
        if market_type == 'cn':
            stock_config = [i for i in stock_config if 'A' in  i['securityTypeName']]
        else:
            stock_config = [i for i in stock_config if i['securityTypeName'] =='美股']

        if stock_config:
            stock_config = stock_config[0]
        market = stock_config['market']
        _end_year_1 = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        _end_year = int(now_time[:4])
        _start_date = int(start_date[:4])
        limit = (_end_year - _start_date + 1) * 250
        klines = dfcf_api.get_stock_kline_data(parameter, market, limit)
        all_kline = _get_kline(klines, _start_date=start_date, _end_date=end_date)
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
