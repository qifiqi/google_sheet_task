import time
import traceback
from typing import Any, Dict

from tenacity import retry, retry_if_result, stop_after_attempt, wait_exponential

from app.exceptions.checkForErrors import checkForErrors
from app.models import TaskResultReturn, db
from app.services.base_multi_sheet_google_sheet_service import BaseMultiSheetGoogleSheetService
from app.services.xpl_service import xpl_analyzer
from app.utils.database import safe_db_operation
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value
from app.utils.yf_api import YFApi


class GoogleSheetService(BaseMultiSheetGoogleSheetService):
    """Google Sheet C5 服务。"""

    service_label = "Google Sheet"
    advisory_lock_tag = "(C5)"
    use_advisory_lock = True

    def __init__(self, config: Dict[str, Any], task_id: str, event_queue=None, app=None):
        super().__init__(config, task_id, event_queue=event_queue, app=app)
        self.xpl = xpl_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()

    def _build_batch_plan(self, parameters, config_data: Dict[str, Any]) -> dict[str, Any]:
        """构建 C5 的批处理执行计划。"""
        count_mode = config_data.get("count_mode", "n_plus_1")
        price_mode = config_data.get("price_mode", "kp_price")
        date_range_mode = config_data.get("date_range_mode", [])
        end_date = config_data.get("end_date")
        start_date = config_data.get("start_date")
        market_type = config_data.get("market_type")

        batches = []
        total_combinations = 0
        for stock_code in parameters[0]:
            combinations, column_a_length, kline_data_map = self._get_all_parameters(
                stock_code,
                count_mode,
                price_mode,
                end_date,
                start_date,
                market_type,
                date_range_mode,
                parameters,
            )
            batches.append(
                {
                    "stock_code": stock_code,
                    "column_a_length": column_a_length,
                    "kline_data_map": kline_data_map,
                    "items": combinations,
                }
            )
            total_combinations += len(combinations)

        return {
            "total_combinations": total_combinations,
            "initial_wait_seconds": 20,
            "batches": batches,
        }

    def _create_runtime_context(self, config_data: Dict[str, Any]) -> dict[str, Any]:
        """维护 C5 复用同源 K 线时的缓存上下文。"""
        return {"cache_parameters": {"combination": {}}}

    def _execute_batch_item(
        self,
        *,
        batch: dict[str, Any],
        item: Any,
        config_data: Dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> tuple[bool, Dict[str, Any], dict[str, Any]]:
        """执行 C5 的单个参数组合。"""
        cache_parameters = runtime_context["cache_parameters"]
        success, result = self._execute_parameter_combination(
            batch["column_a_length"],
            item,
            cache_parameters,
            config_data,
            batch["kline_data_map"],
        )

        kline = batch["kline_data_map"].get(item["Kline_key"])
        save_payload = {
            **item,
            "stock_code": item["stock_code"],
            "kline": [kline[0], kline[-1]],
        }
        return success, result, save_payload

    def _after_item_success(
        self,
        *,
        item: Any,
        result: Dict[str, Any],
        runtime_context: dict[str, Any],
        current_step: int,
    ) -> None:
        """成功后缓存当前组合，减少同源 K 线的重复写入。"""
        runtime_context["cache_parameters"]["combination"] = item

    def _get_input_columns(self, config_data: Dict[str, Any]) -> tuple[str, str]:
        """返回 C5 的输入列范围。"""
        return (
            config_data.get("c5_input_column_a").upper(),
            config_data.get("c5_input_column_b").upper(),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
        retry=retry_if_result(lambda result: result[0] is False),
    )
    def _execute_parameter_combination(
        self,
        column_A_length,
        combination,
        cache_parameters,
        config_data: Dict[str, Any],
        KLINE_DATA_MAP,
    ) -> tuple[bool, Dict[str, Any]]:
        """执行单个参数组合。"""
        try:
            c5_input_column_a = config_data.get("c5_input_column_a").upper()
            c5_input_column_b = config_data.get("c5_input_column_b").upper()
            c5_output_range_1 = config_data.get("c5_output_range_1")
            c5_output_range_2 = config_data.get("c5_output_range_2")
            c5_parameter_positions = config_data.get("c5_parameter_positions")
            c5_output_column_j = config_data.get("c5_output_column_j")
            c5_output_column_l = config_data.get("c5_output_column_l")

            initial_results = {}
            cell_updates = {}
            cell_updates[c5_parameter_positions[0]] = f"xm:{combination[c5_parameter_positions[0]]}"
            cell_updates[c5_parameter_positions[1]] = f"ml:{combination[c5_parameter_positions[1]]}"

            def set_google_values(initial_result_sleep=None):
                kline_key = combination["Kline_key"]
                cached_combination = cache_parameters["combination"]
                cached_kline_key = cached_combination.get("Kline_key", "")
                kline = KLINE_DATA_MAP.get(kline_key)
                kline_length = len(kline)

                if kline_key != cached_kline_key or initial_result_sleep is not None:
                    for google_sheet in self.google_sheets:
                        row_count = column_A_length
                        self._log_info(
                            f"{google_sheet.title} 当前 A 列行数 {row_count}，预写入长度 {kline_length}，准备清空输入区"
                        )
                        google_sheet.clear_range(f"{c5_input_column_a}2:{c5_input_column_b}{row_count + 2}")

                    for index, item in enumerate(kline):
                        cell_num = index + 2
                        cell_updates[f"{c5_input_column_a}{cell_num}"] = item.get("stock_date", "")
                        cell_updates[f"{c5_input_column_b}{cell_num}"] = item.get("stock_val", "")
                else:
                    self._log_info(
                        f"检测到同源数据，仅更新参数位即可，combination:{combination}, "
                        f"cache_parameters:{cache_parameters}"
                    )

                if initial_result_sleep:
                    self._log_info(f"刷新参数后等待 {initial_result_sleep} 秒")
                    time.sleep(initial_result_sleep)

                for google_sheet in self.google_sheets:
                    initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(c5_output_range_1)

                for google_sheet in self.google_sheets:
                    self._log_info(f"向 Google Sheet 写入参数: {google_sheet.title}，单元格数量 {len(cell_updates)}")
                    google_sheet.update_jumped_cells(cell_updates)

            set_google_values()
            kline_key = combination["Kline_key"]
            kline = KLINE_DATA_MAP.get(kline_key)

            def check_result(check_values):
                checked_values = {}
                for position, value in check_values.items():
                    if not value or not is_valid_result_value(value):
                        self._log_info(f"结果位置 {position} 值为空或无效，触发重试: {value}")
                        raise Exception(f"结果位置 {position} 值为空或无效，触发重试: {value}")

                    if str(value).strip().startswith(("#", "#N/A")):
                        error_msg = f"获取结果位置 {position} 时出错: {str(value)}"
                        raise checkForErrors(f"检查报错，出现 # 或 #N/A 异常，请联系用户排查: {error_msg}")

                    if "%" in value:
                        value = float(value.replace("%", "").replace(",", "")) / 100
                    if isinstance(value, str) and "," in value:
                        value = float(value.replace(",", ""))
                    if value == "-":
                        continue
                    checked_values[position] = value
                return checked_values

            def validate_check_values(check_values: Dict[str, Any], spreadsheet_id) -> bool:
                """校验结果区是否已经刷新完成。"""
                if not check_values:
                    return False

                initial_check_values = initial_results[spreadsheet_id]
                prefix = c5_output_range_1[0]
                return not (
                    initial_check_values[f"{prefix}2"] == check_values[f"{prefix}2"]
                    and initial_check_values[f"{prefix}3"] == check_values[f"{prefix}3"]
                )

            def before_attempt(attempt: int):
                """定期刷新参数，避免模型卡住。"""
                if attempt != 0 and (attempt % 10 == 0 or attempt in [5, 15, 25, 35]):
                    self._log_info("触发周期性参数刷新")
                    set_google_values(20)

            def poll_single_sheet(attempt: int, google_sheet):
                result_range = google_sheet.get_range(c5_output_range_1)
                if not validate_check_values(result_range, google_sheet.spreadsheet_id):
                    self._log_warning(f"第 {attempt + 1} 次检查执行状态，当前尚未完成")
                    self._log_warning(
                        f"第 {attempt + 1} 次检查执行状态，结果: {result_range}，初始值: "
                        f"{initial_results[google_sheet.spreadsheet_id]}"
                    )
                    return {"completed": False}

                result_yearly = google_sheet.get_range(c5_output_range_2)
                result_range.update(result_yearly)

                try:
                    index_return = check_result(
                        google_sheet.get_range(f"{c5_output_column_j}2:{c5_output_column_j}{len(kline) + 1}")
                    )
                    start_return = check_result(
                        google_sheet.get_range(f"{c5_output_column_l}2:{c5_output_column_l}{len(kline) + 1}")
                    )
                except Exception as exc:
                    self._log_info(
                        f"获取收益明细区失败: {c5_output_column_j}2:{c5_output_column_j}{len(kline) + 1}，"
                        f"错误: {str(exc)}"
                    )
                    self._log_info(
                        f"当前结果: {result_range}，初始值: {initial_results[google_sheet.spreadsheet_id]}"
                    )
                    return {"completed": False}

                index_return_date = []
                start_return_date = []
                index_start_return_date = []
                for index, item in enumerate(kline):
                    index_return_date.append(
                        {
                            "stock_date": item.get("stock_date"),
                            "stock_val": index_return[f"{c5_output_column_j}{index + 2}"],
                        }
                    )
                    start_return_date.append(
                        {
                            "stock_date": item.get("stock_date"),
                            "stock_val": start_return[f"{c5_output_column_l}{index + 2}"],
                        }
                    )
                    index_start_return_date.append(
                        {
                            "stock_date": item.get("stock_date"),
                            "index_return": index_return[f"{c5_output_column_j}{index + 2}"],
                            "start_return": start_return[f"{c5_output_column_l}{index + 2}"],
                        }
                    )

                result_range["index_return_xpl"] = self.xpl.get_xpl(index_return_date, "stock_date", "stock_val")
                result_range["start_return_xpl"] = self.xpl.get_xpl(start_return_date, "stock_date", "stock_val")
                result_range["_index_start_return_date"] = index_start_return_date
                return {
                    "completed": True,
                    "result_key": f"{google_sheet.spreadsheet_id}__{google_sheet.title}",
                    "result": result_range,
                }

            return self._poll_multi_sheet_results(
                poll_single_sheet=poll_single_sheet,
                before_attempt=before_attempt,
            )
        except Exception as exc:
            error_msg = f"执行参数组合时出错: {traceback.format_exc()}"
            self._log_error(error_msg)
            raise exc

    def _save_task_result(self, step_index: int, parameters, result: Dict, success: bool):
        """保存 C5 任务结果，并补充收益曲线扩展数据。"""
        result_payload = dict(result)
        index_start_return_date = result_payload.pop("_index_start_return_date", None)

        # 基础结果先复用父类保存，确保三套实现共用同一条主保存链路。
        super()._save_task_result(step_index, parameters, result_payload, success)

        if not index_start_return_date:
            return

        def save_result_return_operation():
            for item in index_start_return_date:
                task_result_return = TaskResultReturn(
                    task_id=self.task_id,
                    stock_date=item["stock_date"],
                    index_return=item["index_return"],
                    start_return=item["start_return"],
                )
                db.session.add(task_result_return)
            db.session.commit()

        try:
            if self.app:
                with self.app.app_context():
                    safe_db_operation(save_result_return_operation)
            else:
                from flask import current_app

                with current_app.app_context():
                    safe_db_operation(save_result_return_operation)
        except Exception as exc:
            self._log_error(f"保存任务扩展结果失败: {str(exc)}")

    def _get_all_parameters(
        self,
        parameter,
        count_mode,
        price_mode,
        end_date,
        start_date,
        market_type,
        date_range_mode,
        parameters,
    ):
        """生成 C5 的参数组合与 K 线映射。"""

        def get_kline(klines, year=None, range_start=None, range_end=None):
            price_field = "stock_kp" if price_mode == "kp_price" else "stock_sp"
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

        end_year = int(end_date[:4])
        now_time = time.strftime("%Y-%m-%d", time.localtime(time.time()))
        current_year = int(now_time[:4])
        start_year = int(start_date[:4])
        limit = (current_year - start_year + 1) * 300

        if market_type == "cn":
            stock_config = self.dfcf_api.get_search_list_by_stock_code(parameter, 10)
            stock_config = [item for item in stock_config if "A" in item["securityTypeName"]]
            if stock_config:
                stock_config = stock_config[0]
            market = stock_config["market"]
            klines = self.dfcf_api.get_stock_kline_data(parameter, market, limit)
        else:
            klines = self.YF_api.get_kline_data(parameter, "10y")

        data_start_date = klines[0]["stock_date"]
        data_end_date = klines[-1]["stock_date"]
        if start_date < data_start_date or end_date > data_end_date:
            raise Exception(
                f"股票 {parameter} 设定区间 [{start_date}, {end_date}] 不在 K 线数据范围 "
                f"[{data_start_date}, {data_end_date}] 内"
            )

        if len(klines) < 100:
            raise Exception(f"股票 {parameter} K 线数据量不足 100 条，无法支撑当前模型计算")

        all_kline = get_kline(klines, range_start=start_date, range_end=end_date)
        data = []
        kline_data_map = {}

        base_kline_key = f"{current_year}-{start_year}"
        for value_1 in parameters[1]:
            for value_2 in parameters[2]:
                if base_kline_key not in kline_data_map:
                    kline_data_map[base_kline_key] = all_kline
                data.append(
                    {
                        "stock_code": parameter,
                        "A1": value_1,
                        "B1": value_2,
                        "year": base_kline_key,
                        "Kline_key": base_kline_key,
                    }
                )

        if count_mode != "n_plus_1":
            return data, len(all_kline) + 20, kline_data_map

        if "recent" in date_range_mode:
            for year_offset in range(1, (end_year - start_year) + 1):
                actual_offset = year_offset - 1 if year_offset != 0 else year_offset
                recent_end = f"{end_year - actual_offset}{end_date[4:]}"
                recent_start = f"{end_year - year_offset}{end_date[4:]}"
                kline = get_kline(klines, range_start=recent_start, range_end=recent_end)
                kline_key = f"{recent_end[:4]}-{recent_start[:4]}"
                for value_1 in parameters[1]:
                    for value_2 in parameters[2]:
                        if kline and kline_key not in kline_data_map:
                            kline_data_map[kline_key] = kline
                        data.append(
                            {
                                "A1": value_1,
                                "B1": value_2,
                                "stock_code": parameter,
                                "year": kline_key,
                                "Kline_key": kline_key,
                            }
                        )

        if "full" in date_range_mode:
            filtered_kline = [item for item in klines if start_date <= item["stock_date"] <= end_date]
            for year in range(start_year, end_year + 1):
                kline = get_kline(filtered_kline, year=year)
                for value_1 in parameters[1]:
                    for value_2 in parameters[2]:
                        if kline and year not in kline_data_map:
                            kline_data_map[year] = kline
                        data.append(
                            {
                                "A1": value_1,
                                "B1": value_2,
                                "stock_code": parameter,
                                "year": year,
                                "Kline_key": year,
                            }
                        )

        return data, len(all_kline) + 20, kline_data_map


if __name__ == "__main__":
    GoogleSheetService({}, "")._get_all_parameters(
        "QQQ",
        "n_plus_1",
        "kp_price",
        "2025-05-01",
        "2023-05-01",
        "en",
        ["full", "recent"],
        [[], [1, 2], [1, 2]],
    )
