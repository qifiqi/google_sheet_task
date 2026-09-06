import json
import time
from typing import Dict, Any

from flask import current_app
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

from app.repositories import task_repository, task_result_repository
from app.exceptions.sheet_check_error import SheetCheckError
from app.services.google_sheet_tasks.base import BaseGoogleSheetService, build_execute_task_alert, should_alert_execute_task_result
from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.services.google_sheet_tasks.check_policy import C5_INVALID, normalize_check_values
from app.services.stock_metadata_service import upsert_stock_metadata_in_session
from app.utils.alert_decorator import alert_on_failure
from app.utils.db_retry import safe_db_operation
from app.utils.dfcf_api import DFCJStockApi
from app.utils.result_validator import is_valid_result_value
from app.services.xpl_service import xpl_analyzer
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.logger import get_logger
from app.utils.yf_api import YFApi
from app.utils.task_error_utils import unwrap_exception
from app.utils.kline_validation import require_kline_rows
from app.services.google_sheet_tasks.kline_prep import project_and_validate_write_ready
from app.services.kline_service import KlineService, get_kline_price_field
from app.services.google_sheet_tasks.result_payload import build_analyze_fields, build_stock_param_metric_fields


logger = get_logger(__name__)


class C5Service(BaseGoogleSheetService):
    # 去重日志标签（公共去重器见基类）
    _dedupe_label = "C5"

    # get_bdl 外层网络异常打 [NETWORK_RETRYABLE]（与 C7 对齐，2026-09 审计 C4 批次）
    _retryable_outer = True

    """Google Sheet服务 - C5"""

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.google_sheets: list[GoogleSheet] = []
        self.xpl = xpl_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()
        self.kline_service = KlineService(dfcf_api=self.dfcf_api, yahoo_api=self.YF_api)

    @alert_on_failure(
        result_predicate=should_alert_execute_task_result,
        message_builder=build_execute_task_alert,
    )

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
            **build_stock_param_metric_fields(lambda cell: result.get(cell, 0)),
            **build_analyze_fields(analyze_result),
        })
        return payload


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
                # 核心逻辑收敛于 check_policy.normalize_check_values（C4 批次）
                return normalize_check_values(check_values, log_info=self._log_info, invalid_predicate=C5_INVALID)

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
        all_kline = project_and_validate_write_ready(
            self.kline_service,
            parameter=parameter,
            market_type=market_type,
            klines=klines,
            price_mode=price_mode,
            start_date=start_date,
            end_date=end_date,
            data_end_date=data_end_date,
        )
        data = []

        KLINE_DATA_MAP = {}
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
