import time
import traceback
from typing import Any, Dict

from tenacity import retry, retry_if_result, stop_after_attempt, wait_exponential

from app.exceptions.checkForErrors import checkForErrors
from app.services.base_multi_sheet_google_sheet_service import BaseMultiSheetGoogleSheetService
from app.services.xpl_service import xpl_analyzer
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value, validate_result_dict


class GoogleSheetService(BaseMultiSheetGoogleSheetService):
    """Google Sheet C4 服务。"""

    service_label = "Google Sheet"
    advisory_lock_tag = "(C4)"
    use_advisory_lock = True

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None):
        super().__init__(config, task_id, event_queue=event_queue, app=app)
        self.xpl = xpl_analyzer

    def _build_batch_plan(self, parameters, config_data: Dict[str, Any]) -> dict[str, Any]:
        """构建 C4 的批处理执行计划。"""
        count_mode = config_data.get("count_mode", "n_plus_1")
        date_range_mode = config_data.get("date_range_mode", [])
        end_date = config_data.get("end_date")
        start_date = config_data.get("start_date")
        market_type = config_data.get("market_type")

        batches = []
        total_combinations = 0
        for stock_code in parameters[0]:
            combinations, column_a_length = self._get_all_parameters(
                stock_code,
                count_mode,
                end_date,
                start_date,
                market_type,
                date_range_mode,
            )
            batches.append(
                {
                    "stock_code": stock_code,
                    "column_a_length": column_a_length,
                    "items": combinations,
                }
            )
            total_combinations += len(combinations)

        return {
            "total_combinations": total_combinations,
            "initial_wait_seconds": 20,
            "batches": batches,
        }

    def _execute_batch_item(
        self,
        *,
        batch: dict[str, Any],
        item: Any,
        config_data: Dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> tuple[bool, Dict[str, Any], dict[str, Any]]:
        """执行 C4 的单个参数组合。"""
        success, result = self._execute_parameter_combination(
            batch["column_a_length"],
            item,
            config_data,
        )
        save_payload = {
            "stock_code": item["stock_code"],
            "kline": [item["kline"][0], item["kline"][-1]],
        }
        return success, result, save_payload

    def _get_input_columns(self, config_data: Dict[str, Any]) -> tuple[str, str]:
        """返回 C4 的输入列范围。"""
        return (
            config_data.get("c4_input_column_a").upper(),
            config_data.get("c4_input_column_b").upper(),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
        retry=retry_if_result(lambda result: result[0] is False),
    )
    @validate_result_dict(
        none_values=(None, "", " ", "#N/A", "#DIV/0!", "#ERROR!", "#VALUE!", "#REF!", "#NAME?", "#NUM!")
    )
    def _execute_parameter_combination(
        self,
        column_A_length,
        combination,
        config_data: Dict[str, Any],
    ) -> tuple[bool, Dict[str, Any]]:
        """执行单个参数组合。"""
        try:
            c4_input_column_a = config_data.get("c4_input_column_a").upper()
            c4_input_column_b = config_data.get("c4_input_column_b").upper()
            c4_output_range_1 = config_data.get("c4_output_range_1")
            c4_output_range_2 = config_data.get("c4_output_range_2")
            c4_output_column_j = config_data.get("c4_output_column_j")
            c4_output_column_l = config_data.get("c4_output_column_l")

            for google_sheet in self.google_sheets:
                row_count = column_A_length
                self._log_info(f"{google_sheet.title} 当前 A 列行数 {row_count}，准备清空 A/B 输入区")
                google_sheet.clear_range(f"{c4_input_column_a}2:{c4_input_column_b}{row_count + 2}")

            initial_results = {}
            cell_updates = {}
            kline = combination["kline"]

            for index, item in enumerate(kline):
                cell_num = index + 2
                cell_updates[f"{c4_input_column_a}{cell_num}"] = item.get("stock_date", "")
                cell_updates[f"{c4_input_column_b}{cell_num}"] = item.get("stock_val", "")

            for google_sheet in self.google_sheets:
                self._log_info(f"向 Google Sheet 写入参数: {google_sheet.title}，单元格数量 {len(cell_updates)}")
                google_sheet.update_jumped_cells(cell_updates)
                initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c4_output_range_1)

            def check_result(check_values):
                checked_values = {}
                for position, value in check_values.items():
                    if not value or not is_valid_result_value(value):
                        self._log_info(f"结果位置 {position} 值为空或无效，触发重试")
                        raise Exception(f"结果位置 {position} 值为空或无效，触发重试")

                    if str(value).strip().startswith(("#", "#N/A")):
                        error_msg = f"获取结果位置 {position} 时出错: {str(value)}"
                        raise checkForErrors(f"检查报错，出现 # 或 #N/A 异常，请联系用户排查: {error_msg}")

                    if "%" in value:
                        value = float(value.replace("%", "").replace(",", "")) / 100
                    if isinstance(value, str):
                        value = float(value.replace(",", ""))
                    checked_values[position] = value
                return checked_values

            def validate_check_values(check_values: Dict[str, Any], spreadsheet_id) -> bool:
                """校验结果区是否已经刷新完成。"""
                if not check_values:
                    return False

                for position, value in check_values.items():
                    if not value or value in ["#DIV/0!", "", "#N/A", "#ERROR!", "#VALUE!"]:
                        return False
                    if "target" in str(value).lower():
                        return False

                initial_check_values = initial_results[spreadsheet_id]
                if (
                    initial_check_values["D2"] == check_values["D2"]
                    and initial_check_values["D3"] == check_values["D3"]
                ):
                    return False

                return True

            def poll_single_sheet(attempt: int, google_sheet):
                self._log_info(f"轮询 Google Sheet 结果: {google_sheet.title}")
                result_range = google_sheet.get_range(c4_output_range_1)
                if not validate_check_values(result_range, google_sheet.spreadsheet_id):
                    self._log_warning(f"第 {attempt + 1} 次检查执行状态，当前尚未完成")
                    self._log_warning(
                        f"第 {attempt + 1} 次检查执行状态，结果: {result_range}，初始值: "
                        f"{initial_results[google_sheet.spreadsheet_id]}"
                    )
                    return {"completed": False}

                result_yearly = google_sheet.get_range(c4_output_range_2)
                index_return = check_result(
                    google_sheet.get_range(f"{c4_output_column_j}2:{c4_output_column_j}{len(kline) + 1}")
                )
                start_return = check_result(
                    google_sheet.get_range(f"{c4_output_column_l}2:{c4_output_column_l}{len(kline) + 1}")
                )

                index_return_date = []
                start_return_date = []
                for index, item in enumerate(kline):
                    index_return_date.append(
                        {
                            "stock_date": item.get("stock_date"),
                            "stock_val": index_return[f"{c4_output_column_j}{index + 2}"],
                        }
                    )
                    start_return_date.append(
                        {
                            "stock_date": item.get("stock_date"),
                            "stock_val": start_return[f"{c4_output_column_l}{index + 2}"],
                        }
                    )

                result_range.update(result_yearly)
                result_range["index_return_xpl"] = self.xpl.get_xpl(index_return_date, "stock_date", "stock_val")
                result_range["start_return_xpl"] = self.xpl.get_xpl(start_return_date, "stock_date", "stock_val")
                return {
                    "completed": True,
                    "result_key": f"{google_sheet.spreadsheet_id}__{google_sheet.title}",
                    "result": result_range,
                }

            def retry_refresh(attempt: int):
                if attempt not in [5, 15, 25, 35]:
                    return

                for google_sheet in self.google_sheets:
                    self._log_info(f"重新刷新 Google Sheet 参数: {google_sheet.title}")
                    google_sheet.update_jumped_cells(cell_updates)

                time.sleep(30)
                for google_sheet in self.google_sheets:
                    self._log_info(f"刷新后重新读取初始结果: {google_sheet.title}")
                    initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c4_output_range_1)

            return self._poll_multi_sheet_results(
                poll_single_sheet=poll_single_sheet,
                retry_refresh=retry_refresh,
            )
        except Exception as exc:
            error_msg = f"执行参数组合时出错: {traceback.format_exc()}"
            self._log_error(error_msg)
            raise exc

    @staticmethod
    def _get_all_parameters(parameter, count_mode, end_date, start_date, market_type, date_range_mode):
        """生成 C4 的参数组合。"""

        def get_kline(klines, year=None, range_start=None, range_end=None):
            price_field = "stock_kp" if market_type == "cn" else "stock_sp"
            if year:
                return [
                    {"stock_date": item["stock_date"], "stock_val": item[price_field]}
                    for item in klines
                    if int(item["stock_date"][:4]) == year
                ]
            return [
                {"stock_date": item["stock_date"], "stock_val": item[price_field]}
                for item in klines
                if range_start <= item["stock_date"] <= range_end
            ]

        dfcf_api = DFCJStockApi()
        stock_config = dfcf_api.get_search_list_by_stock_code(parameter, 10)
        if market_type == "cn":
            stock_config = [item for item in stock_config if "A" in item["securityTypeName"]]
        else:
            stock_config = [item for item in stock_config if item["securityTypeName"] == "美股"]

        if stock_config:
            stock_config = stock_config[0]
        market = stock_config["market"]
        end_year = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        current_year = int(now_time[:4])
        start_year = int(start_date[:4])
        limit = (current_year - start_year + 1) * 250
        klines = dfcf_api.get_stock_kline_data(parameter, market, limit)
        all_kline = get_kline(klines, range_start=start_date, range_end=end_date)
        data = [{"stock_code": parameter, "kline": all_kline}]

        if count_mode != "n_plus_1":
            return data, len(all_kline) + 20

        if "recent" in date_range_mode:
            for year_offset in range(1, (end_year - start_year) + 1):
                actual_offset = year_offset - 1 if year_offset != 0 else year_offset
                recent_end = f"{end_year - actual_offset}{end_date[4:]}"
                recent_start = f"{end_year - year_offset}{end_date[4:]}"
                kline = get_kline(klines, range_start=recent_start, range_end=recent_end)
                if kline:
                    data.append({"stock_code": parameter, "kline": kline})

        if "full" in date_range_mode:
            filtered_kline = [item for item in klines if start_date <= item["stock_date"] <= end_date]
            for year in range(start_year, end_year + 1):
                kline = get_kline(filtered_kline, year=year)
                if kline and len(kline) > 30:
                    data.append({"stock_code": parameter, "year": year, "kline": kline})

        return data, len(all_kline) + 20


if __name__ == "__main__":
    GoogleSheetService({}, "")._get_all_parameters("000001", "n_plus_1", "2025-05-01", "2023-05-01", "cn", [])
