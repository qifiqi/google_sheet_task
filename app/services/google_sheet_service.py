import random
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from tenacity import retry, retry_if_result, stop_after_attempt, wait_exponential

from app.exceptions.checkForErrors import checkForErrors
from app.services.base_single_sheet_google_sheet_service import BaseSingleSheetGoogleSheetService
from app.services.config_manager import get_config_manager
from app.utils.google_sheet_result_helper import parse_result_value
from app.utils.logger import get_logger
from app.utils.result_validator import (
    is_valid_result_value,
    validate_google_sheet_result,
    validate_result_dict,
)

logger = get_logger(__name__)


class GoogleSheetService(BaseSingleSheetGoogleSheetService):
    """默认 Google Sheet 服务。"""

    service_label = "Google Sheet"

    def _run_task(self, task, name, parameters, config_data):
        """执行默认版本的批处理主流程。"""
        stock_param = self.get_single_stock_template_param(name)
        final_status = None

        if stock_param is not None and stock_param != "error":
            multiplier_index = (
                0
                if stock_param.get("multiplier_index", 0) == 0
                else stock_param.get("multiplier_index", 0) + 1
            )
            self._log_info(f"开始执行参数批量处理，multiplier_index: {multiplier_index}")
            success_count, failed_count, task_status = self.get_bdl(
                task,
                name,
                parameters,
                config_data,
                multiplier_index,
            )
            final_status = "completed" if success_count > 0 else "error"
        elif stock_param != "error":
            self._log_info("开始执行参数批量处理（默认参数模式）")
            success_count, failed_count, task_status = self.get_bdl(task, name, parameters, config_data)
        else:
            self._log_error("获取股票参数失败")
            return {"success_count": 0, "failed_count": 0, "task_status": "error"}

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "task_status": task_status,
            "final_status": final_status,
        }

    def _execute_batch_item(
        self,
        *,
        combination: Any,
        config_data: Dict[str, Any],
        item_index: int,
    ) -> tuple[bool, Dict[str, Any], dict[str, Any], dict[str, Any]]:
        """执行默认版的单个参数组合。"""
        success, result = self._execute_parameter_combination(combination, config_data)
        save_payload = combination
        extension_payload = {
            "stock_no": self.task.name if self.task else "",
            "multiplier": result["B6"],
            "danbian": result["B7"],
            "xiancang": result["B9"],
            "zhishu": result["B10"],
            "smoothing": result["B11"],
            "bordering": result["B12"],
            "multiplier_index": item_index,
            "danbian_index": 0,
            "xiancang_index": 0,
            "zhishu_index": 0,
            "smoothing_index": 0,
            "bordering_index": 0,
            "return_rate": result["I15"],
            "annualized_rate": result["I16"],
            "maxdd": result["I17"],
            "index_rate": result["I18"],
            "index_annualized_rate": result["I19"],
            "max_index_dd": result["I20"],
            "fee_total": result["I21"],
            "fee_annualized": result["I22"],
            "year_rate": result["I23"],
        }
        return success, result, save_payload, extension_payload

    def _after_item_success(
        self,
        *,
        combination: Any,
        result: Dict[str, Any],
        extension_payload: dict[str, Any],
    ) -> None:
        """执行成功后同步参数结果到生产数据源。"""
        self.send_stock_template_param_data(extension_payload, lambda level, msg: self._log(level, msg))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
        retry=retry_if_result(lambda result: result[0] is False),
    )
    @validate_result_dict(
        none_values=(None, "", " ", "#N/A", "#DIV/0!", "#ERROR!", "#VALUE!", "#REF!", "#NAME?", "#NUM!")
    )
    def _execute_parameter_combination(self, combination: List, config_data: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """执行单个参数组合。"""
        try:
            param_positions = config_data.get("parameter_positions", [])
            check_positions = config_data.get("check_positions", [])
            result_positions = config_data.get("result_positions", [])

            results = {}
            cell_updates = {}

            def update_cell(attempt_index=0):
                for index, position in enumerate(param_positions):
                    cell_updates[position] = combination[index]
                    results[position] = combination[index]

                if attempt_index <= 0:
                    self._log_info(f"向 Google Sheet 写入参数: {cell_updates}")
                    self.google_sheet.update_jumped_cells(cell_updates)
                    return

                random_key = random.choice(list(cell_updates.keys()))
                random_value = cell_updates[random_key]
                self._log_info(
                    f"防止模型卡顿，在随机位置写入: {random_key} = {random_value}，当前第 {attempt_index + 1} 轮检查"
                )

                if random_value is None or str(random_value).strip() == "":
                    self._log_warning(f"跳过写入空值到位置 {random_key}")
                    return

                try:
                    self.google_sheet.update_cell(random_key, random_value)
                except Exception as exc:
                    self._log_error(f"更新单元格 {random_key} 失败，值: {random_value}，错误: {str(exc)}")
                    raise

            def check_result(position, value=None):
                parsed_value = parse_result_value(position, value)
                results[position] = round(parsed_value, 5)

            def validate_check_values(check_values: Dict[str, Any]) -> bool:
                """校验检查位是否已经刷新完成。"""
                if not check_values:
                    return False

                for position, value in check_values.items():
                    if not value or value in ["#DIV/0!", "", "#N/A", "#ERROR!", "#VALUE!"]:
                        return False
                    if "target" in str(value).lower():
                        return False

                    input_key = f"B{position[1:]}"
                    if input_key in results:
                        try:
                            check_val = float(value.replace("%", "")) / 100 if "%" in value else float(value)
                            input_val = float(results[input_key])
                            if round(check_val) != round(input_val):
                                return False
                        except (ValueError, TypeError):
                            return False

                return True

            def validate_result_values(result_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
                """校验结果位是否完整有效。"""
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

                error_msgs = []
                if missing_positions:
                    error_msgs.append(f"缺少位置: {missing_positions}")
                if invalid_positions:
                    error_msgs.append(f"无效值: {invalid_positions}")
                return len(error_msgs) == 0, error_msgs

            sleep_num = 5

            def get_delay_seconds(min_sleep: int, max_sleep: int) -> int:
                nonlocal sleep_num
                if sleep_num <= 0:
                    sleep_num = 5
                delay_seconds = min(min_sleep + sleep_num * 5, max_sleep)
                sleep_num -= 1
                return int(delay_seconds)

            update_cell()
            fallback_error_count = 0
            max_error_num = 3

            for attempt in range(60):
                if attempt != 0 and (attempt % 10 == 0 or attempt in [3, 5, 8]):
                    self._log_info(f"第 {attempt + 1} 次检查执行状态前，刷新表格参数")
                    update_cell(attempt)

                config_manager = get_config_manager()
                delay_min = int(config_manager.get_config("execution_delay_min", 20))
                delay_max = int(config_manager.get_config("execution_delay_max", 30))
                delay_seconds = get_delay_seconds(delay_min, delay_max)
                self._log_info(f"第 {attempt + 1} 次检查执行状态，等待 {delay_seconds} 秒")
                time.sleep(delay_seconds)

                all_completed = True
                if self.google_sheet and check_positions:
                    try:
                        check_values = self.google_sheet.get_cells_batch(check_positions)
                        self._log_info(f"获取到检查位置的值: {check_values}")
                        if not validate_check_values(check_values):
                            all_completed = False
                            self._log_info("检查位置验证失败，继续等待")
                            continue
                    except Exception as exc:
                        self._log_error(f"批量检查位置时出错: {str(exc)}")
                        all_completed = False
                        continue

                if all_completed and self.google_sheet and result_positions:
                    try:
                        result_values = self.google_sheet.get_cells_batch(result_positions)
                        self._log_info(f"获取到参数执行结果: {result_values}")

                        is_valid, error_msgs = validate_result_values(result_values)
                        if not is_valid:
                            self._log_warning(f"结果验证失败: {error_msgs}，继续等待")
                            all_completed = False
                            continue

                        for position in result_positions:
                            value = result_values.get(position, "")
                            check_result(position, value)

                        is_valid_gs, gs_error_msg = validate_google_sheet_result(results)
                        if not is_valid_gs:
                            self._log_warning(f"Google Sheet 结果验证失败: {gs_error_msg}")
                            return False, {}

                        self._log_info(f"参数组合执行成功，结果: {results}")
                        return True, results
                    except checkForErrors:
                        raise
                    except Exception as exc:
                        self._log_error(f"批量获取结果时出错: {str(exc)}")
                        fallback_error_count += 1
                        if fallback_error_count <= max_error_num:
                            continue

                        fallback_success = True
                        for position in result_positions:
                            try:
                                value = self.google_sheet.get_cell(position)
                                check_result(position, value)
                            except Exception as cell_error:
                                self._log_error(f"获取结果位置 {position} 时出错: {str(cell_error)}")
                                fallback_success = False
                                break

                        if fallback_success:
                            is_valid_gs, gs_error_msg = validate_google_sheet_result(results)
                            if is_valid_gs:
                                return True, results

                            self._log_warning(f"回退模式结果验证失败: {gs_error_msg}")
                            return False, {}

            self._log_warning("执行超时，未在规定时间内完成")
            return False, {}
        except Exception as exc:
            self._log_error(f"执行参数组合时出错: {traceback.format_exc()}")
            raise exc

    def _get_parameter_combination_by_index(self, parameters: List[List], index: int) -> List:
        """根据索引按需计算参数组合，避免一次性展开。"""
        try:
            logger.debug(f"计算第 {index} 个参数组合")
            combination = []
            remaining_index = index

            for param_list in reversed(parameters):
                param_index = remaining_index % len(param_list)
                combination.insert(0, param_list[param_index])
                remaining_index = remaining_index // len(param_list)

            return combination
        except Exception as exc:
            self._log_error(f"计算参数组合失败，索引 {index}，错误: {str(exc)}")
            raise
