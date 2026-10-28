from typing import Dict, Any

from app.services.google_sheet_tasks.base import (
    BaseGoogleSheetService,
    build_execute_task_alert,
    calculate_index_returns_from_closes,
    parse_range_start,
    should_alert_execute_task_result,
)
from app.services.google_sheet_client import GoogleSheet
from app.utils.alert_decorator import alert_on_failure
from app.utils.dfcf_api import DFCJStockApi
from app.utils.value_parser import coerce_bool
from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.utils.logger import get_logger
from app.utils.yf_api import YFApi
from app.utils.kline_validation import require_kline_rows
from app.services.google_sheet_tasks.check_policy import C7_INVALID, normalize_check_values
from app.services.google_sheet_tasks.result_payload import (
    build_analyze_fields,
    build_c1_1_summary_fields,
    to_decimal_ratio,
)
from app.services.kline_service import KlineService


logger = get_logger(__name__)

# C1.1 结果块取值列（模板 E 列为标签、F 列为值），可经 SystemConfig/task config 的 c1_1_output_range 覆盖
C1_1_DEFAULT_OUTPUT_RANGE = "F2:F26"


def _annualized_collapsed(value: Any) -> bool:
    """年化收益跌至 -100% 及以下（本金归零）时视为终态，不再等待其余信号刷新。"""
    return to_decimal_ratio(value) <= -0.9


class C1_1Service(BaseGoogleSheetService):
    """Google Sheet 服务 - C1.1（无参数组合 + 随机价格 ext 列）。

    与 C5/C7 的差异：无参数组合输入；组合维度 = K线窗口 × 随机分组
    （random_price 机制），K线写入 date/o/h/l/c/vwap/ext 七列，
    ext 列为随机价；结果读取为 F 列单列结果块 + K 列 start return 序列。
    """

    _retryable_outer = True  # 外层异常需打 [NETWORK_RETRYABLE] 供看门狗识别

    _model_version = "c1_1"

    # 去重日志标签（公共去重器见基类）
    _dedupe_label = "C1.1"

    # 是否计算并写入 vwap 列；_prepare_batch 按任务配置覆盖（缺省计算）。
    _vwap_enabled = True

    def _dedupe_extra_signature(self, combination: dict) -> tuple:
        """C1.1 随机价分组参与去重签名（同组同K线视为重复）。"""
        return (
            str(combination.get('random_group', '')),
            str(combination.get('kline_key', '')) if combination.get('random_group') else '',
        )

    def __init__(self, config: Dict[str, Any], task_id: str, app=None, stop_event=None):
        super().__init__(config, task_id, app=app, stop_event=stop_event)
        self.google_sheets: list[GoogleSheet] = []
        self.performance_analyzer = performance_analyzer
        self.YF_api = YFApi()
        self.dfcf_api = DFCJStockApi()
        self.kline_service = KlineService(dfcf_api=self.dfcf_api, yahoo_api=self.YF_api)
        # custom 模式随机分组配置（_prepare_batch 从 batch 挂载；_get_custom_parameters 用）
        self._random_price_range = "high_low"
        self._random_group_count = 1

    # ---- 布局 ----

    @staticmethod
    def _get_c1_1_layout(config_data: Dict[str, Any], google_sheet=None) -> Dict[str, Any]:
        """构建 C1.1 输入和结果布局（配置键可覆盖，默认见各键回退值）。"""
        return {
            "start_row": int(config_data.get("c1_1_kline_start_row") or 2),
            "date_column": str(config_data.get("c1_1_kline_date_column") or "AA").upper(),
            "open_column": str(config_data.get("c1_1_kline_open_column") or "AB").upper(),
            "high_column": str(config_data.get("c1_1_kline_high_column") or "AC").upper(),
            "low_column": str(config_data.get("c1_1_kline_low_column") or "AD").upper(),
            "close_column": str(config_data.get("c1_1_kline_close_column") or "AE").upper(),
            "vwap_column": str(config_data.get("c1_1_kline_vwap_column") or "AF").upper(),
            "ext_column": str(config_data.get("c1_1_kline_ext_column") or "AG").upper(),
            "output_range": str(config_data.get("c1_1_output_range") or C1_1_DEFAULT_OUTPUT_RANGE).upper(),
            "output_column_k": str(config_data.get("c1_1_output_column_k") or "K").upper(),
        }

    @staticmethod
    def _get_c1_1_input_last_row(google_sheet, layout: Dict[str, Any]) -> int:
        columns = [
            layout["date_column"],
            layout["open_column"],
            layout["high_column"],
            layout["low_column"],
            layout["close_column"],
            layout["vwap_column"],
            layout["ext_column"],
        ]
        rows = [google_sheet.get_last_row(column) for column in dict.fromkeys(columns)]
        return max((row for row in rows if row >= 0), default=0)

    @staticmethod
    def _validate_c1_1_ohlc_rows(rows):
        for index, row in enumerate(rows, start=1):
            for field in ("open", "high", "low", "close"):
                if row.get(field) in (None, ""):
                    raise ValueError(f"C1.1 K线第 {index} 条缺少 OHLC 字段 {field}")

    # ---- get_bdl 模板钩子覆盖（默认实现见基类）----

    def _prepare_batch(self, config_data: dict) -> dict:
        # vwap 开关先落实例：基类 _prepare_batch 会经 _load_custom_kline_map 读 custom 源
        self._vwap_enabled = coerce_bool(config_data.get("c1_1_vwap_enabled"), True)
        batch = super()._prepare_batch(config_data)
        batch["vwap_enabled"] = self._vwap_enabled
        if batch["kline_source"] == "auto" and batch["price_mode"] != "random_price":
            raise ValueError("C1.1 必须使用随机价格（price_mode=random_price）")
        random_price_range = str(batch.get("random_price_range") or "high_low").strip().lower()
        if random_price_range not in ("high_low", "open_close"):
            raise ValueError("随机价格范围仅支持最高最低或开盘收盘")
        batch["random_price_range"] = random_price_range
        batch["random_group_count"] = max(1, int(batch.get("random_group_count") or 1))
        # custom 模式 _get_custom_parameters 签名不含 batch，随机配置挂实例
        self._random_price_range = random_price_range
        self._random_group_count = batch["random_group_count"]
        # C1.1 执行链路（_attempt 等）需要原始配置取布局
        batch["_config_data"] = config_data
        return batch

    def _expand_parameters(self, outer_param, parameters, batch):
        # C1.1 无参数组合输入：内层参数占位为单值，组合维度 = K线窗口 × 随机分组
        data, column_A_length, kline_data_map = self._get_all_parameters(
            outer_param,
            batch["count_mode"],
            batch["price_mode"],
            batch["end_date"],
            batch["start_date"],
            batch["market_type"],
            batch["date_range_mode"],
            batch["exclude_recent_years"],
            [parameters[0], [None], [None]],
            adjust_type=batch["adjust_type"],
            random_price_range=batch["random_price_range"],
            random_group_count=batch["random_group_count"],
            random_series_mode=batch["random_series_mode"],
            data_source=batch["data_source"],
            include_vwap=batch["vwap_enabled"],
        )
        for combination in data:
            combination.pop("A1", None)
            combination.pop("B1", None)
        return data, column_A_length, kline_data_map

    def _get_custom_parameters(self, parameter, parameters, custom_kline_map):
        """custom K线模式：单窗口占位组合 × 随机分组（ext 随机价仍逐组重写）。"""
        source_kline = custom_kline_map.get("custom") or []
        if not self._vwap_enabled:
            source_kline = self._without_vwap(source_kline)
            custom_kline_map = {"custom": source_kline}
        data = [{
            "stock_code": parameter,
            "kline_key": "custom",
        }]
        data, custom_kline_map = self._expand_random_price_groups(
            data,
            custom_kline_map,
            "random_price",
            self._random_price_range,
            self._random_group_count,
            snapshot_meta={
                "stock_name": (self.config or {}).get("stock_name"),
                "market_type": (self.config or {}).get("market_type"),
                # custom 源是 Sheet 现有K线，无外部数据源/复权口径
                "data_source": "custom",
                "adjust_type": None,
            },
        )
        data = self._deduplicate_parameter_combinations(data, custom_kline_map)
        return data, len(source_kline) + 20, custom_kline_map

    @staticmethod
    def _without_vwap(rows):
        """vwap 开关关闭时剔除源行的 vwap 值（custom 源不采用 Sheet 现值）。"""
        return [{key: value for key, value in row.items() if key != "vwap"} for row in rows]

    def _load_custom_kline_map(self, config_data: dict) -> dict:
        layout = self._get_c1_1_layout(config_data)
        return {'custom': self._get_custom_kline_data(layout)}

    def _clear_input_columns(self, google_sheet, batch) -> None:
        config_data = batch["_config_data"]
        layout = self._get_c1_1_layout(config_data, google_sheet)
        last_row = self._get_c1_1_input_last_row(google_sheet, layout)
        if last_row < layout["start_row"]:
            return
        self._log_info(
            f'{google_sheet.title} 当前K线行数: {last_row},准备清空 '
            f'{layout["date_column"]}{layout["start_row"]}:{layout["ext_column"]}{last_row}'
        )
        google_sheet.clear_range(
            f'{layout["date_column"]}{layout["start_row"]}:{layout["ext_column"]}{last_row}'
        )

    def _stamp_combination(self, combination: dict, batch: dict) -> None:
        combination['c1_1_output_range'] = self._get_c1_1_layout(batch["_config_data"])["output_range"]

    def _get_all_parameters(self, parameter, count_mode, price_mode, end_date, start_date, market_type,
                            date_range_mode, exclude_recent_years, parameters, adjust_type=None,
                            random_price_range="high_low", random_group_count=1, data_source="akshare",
                            random_series_mode="per_window", include_vwap=True):
        """auto-K线参数展开复用基类骨架；C1.1 按开关携带 OHLC(+vwap) 写回。"""
        return self._expand_auto_year_parameters(
            parameter,
            count_mode,
            price_mode,
            end_date,
            start_date,
            market_type,
            date_range_mode,
            exclude_recent_years,
            parameters,
            adjust_type=adjust_type,
            data_source=data_source,
            source_label="google_sheet_c1_1",
            include_ohlc=True,
            random_price_range=random_price_range,
            random_group_count=random_group_count,
            random_series_mode=random_series_mode,
            include_vwap=include_vwap,
        )

    # ---- custom K线读取（AA..AF：date/o/h/l/c/vwap）----

    def _get_custom_kline_data(self, layout: Dict[str, Any]) -> list:
        if not self.google_sheets:
            raise ValueError("自定义K线模式缺少 Google Sheet")

        google_sheet = self.google_sheets[0]
        start_row = layout["start_row"]
        last_row = google_sheet.get_last_row(layout["date_column"])
        if last_row < start_row:
            raise ValueError("自定义K线模式下输入列没有K线数据")

        values = google_sheet.get_range(
            f"{layout['date_column']}{start_row}:{layout['vwap_column']}{last_row}"
        )
        rows = []
        for row_num in range(start_row, last_row + 1):
            stock_date = values.get(f"{layout['date_column']}{row_num}")
            open_price = values.get(f"{layout['open_column']}{row_num}")
            high_price = values.get(f"{layout['high_column']}{row_num}")
            low_price = values.get(f"{layout['low_column']}{row_num}")
            close_price = values.get(f"{layout['close_column']}{row_num}")
            vwap_price = values.get(f"{layout['vwap_column']}{row_num}")
            if all(value in (None, "") for value in (stock_date, open_price, high_price, low_price, close_price)):
                continue
            rows.append({
                "stock_date": str(stock_date).strip() if stock_date is not None else "",
                "stock_val": close_price,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "vwap": vwap_price,
            })

        validated = require_kline_rows(
            "custom",
            "custom",
            rows,
            context="自定义K线",
            min_rows=self._get_min_kline_rows(),
            price_field="stock_val",
        )
        self._validate_c1_1_ohlc_rows(validated)
        return validated

    # ---- 执行 ----

    @alert_on_failure(
        result_predicate=should_alert_execute_task_result,
        message_builder=build_execute_task_alert,
    )
    def _execute_parameter_combination(self, column_A_length, combination, cache_parameters,
                                       config_data: Dict[str, Any], kline_data_map) -> tuple[bool, Dict[str, Any]]:
        """执行单个随机价分组（无参数组合：K线窗口 × 随机组）"""
        try:
            initial_results = {}
            results = {}
            sheet_layouts = {
                google_sheet.spreadsheet_id: self._get_c1_1_layout(config_data, google_sheet)
                for google_sheet in self.google_sheets
            }
            kline_key = combination['kline_key']
            is_custom_kline = str(config_data.get('kline_source') or 'auto').strip().lower() == 'custom'
            current_kline = require_kline_rows(
                combination.get('stock_code', ''),
                config_data.get('market_type', ''),
                kline_data_map.get(kline_key),
                context=f"K线区间 {kline_key}",
            )
            self._validate_c1_1_ohlc_rows(current_kline)



            def set_googl_val(initial_result_sleep=None):
                _combination = cache_parameters['combination']
                cache_kline_key = _combination.get('kline_key', "")
                cache_stock_code = str(_combination.get('stock_code') or '').strip()
                current_stock_code = str(combination.get('stock_code') or '').strip()
                kline = current_kline
                kline_changed = (
                    kline_key != cache_kline_key
                    or current_stock_code != cache_stock_code
                    or initial_result_sleep is not None
                )

                if is_custom_kline:
                    self._log_info(f"自定义K线模式，不修改K线列，只写入 ext 随机价 combination:{combination}")
                elif kline_changed:
                    for google_sheet in self.google_sheets:
                        layout = sheet_layouts[google_sheet.spreadsheet_id]
                        last_row = self._get_c1_1_input_last_row(google_sheet, layout)
                        end_row = max(last_row, layout["start_row"] + column_A_length)
                        google_sheet.clear_range(
                            f'{layout["date_column"]}{layout["start_row"]}:{layout["ext_column"]}{end_row}'
                        )
                else:
                    self._log_info(f"同源数据，不需要修改K线，只更新 ext 随机价 combination:{combination}")

                if initial_result_sleep:
                    self._log_info(f"刷新参数等待：{initial_result_sleep}秒")
                    if not self._interruptible_sleep(initial_result_sleep):
                        raise RuntimeError("task cancelled")

                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    initial_results[google_sheet.spreadsheet_id] = google_sheet.get_range(layout["output_range"])


                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    cell_updates = {}
                    if not is_custom_kline and kline_changed:
                        for index, item in enumerate(kline):
                            cell_num = layout["start_row"] + index
                            stock_date = item.get("stock_date", "")
                            # if '-' in item.get("stock_date", ""):
                            #     stock_date = item.get("stock_date").replace("-", "/")


                            cell_updates[f'{layout["date_column"]}{cell_num}'] = stock_date
                            cell_updates[f'{layout["open_column"]}{cell_num}'] = item.get("open", "")
                            cell_updates[f'{layout["high_column"]}{cell_num}'] = item.get("high", "")
                            cell_updates[f'{layout["low_column"]}{cell_num}'] = item.get("low", "")
                            cell_updates[f'{layout["close_column"]}{cell_num}'] = item.get("close", "")
                            if self._vwap_enabled:
                                # vwap 开关关闭：AF 列保持清空后的空值
                                cell_updates[f'{layout["vwap_column"]}{cell_num}'] = item.get("vwap") or ""
                    for index, item in enumerate(kline):
                        cell_num = layout["start_row"] + index
                        cell_updates[f'{layout["ext_column"]}{cell_num}'] = item.get("stock_val", "")
                    self._log_info(f"向Google Sheet写入K线/ext随机价: {google_sheet.title} 长度：{len(cell_updates)}")
                    # USER_ENTERED 让日期字符串按模板 locale 解析为日期值；默认 RAW 会把 AA 列写成文本，模板模型无法按日期处理
                    google_sheet.update_jumped_cells(cell_updates, value_input_option='USER_ENTERED')

            set_googl_val()
            kline = current_kline

            def check_result(check_values):
                # K 列 start return 用严格判定（空值视为未完成）；结果块空值放行由结果块读取层处理
                return normalize_check_values(check_values, log_info=self._log_info, invalid_predicate=C7_INVALID)

            def _validate_check_values(check_values: Dict[str, Any], spreadsheet_id, layout: Dict[str, Any]) -> bool:
                """验证结果块核心单元格已更新且有效。

                变化信号取结果块第 3/4 行（Total Return/MAX DD）：
                Start/End date 可能是静态值，不能作为重算完成信号。
                """
                current_block = check_values.get(layout["output_range"]) or {}
                _check_values = initial_results[spreadsheet_id]
                output_column, output_row = parse_range_start(layout["output_range"])
                for offset in (3, 5):
                    # cell = f"{output_column}{output_row + offset}"
                    cell = f"{output_column}{1 + offset}"
                    if _annualized_collapsed(current_block.get(cell)):
                        self._log_info(
                            f"结果块 {cell} 至 -90% 及以下，直接判定完成：{current_block.get(cell)}"
                        )
                        return True
                    if C7_INVALID(current_block.get(cell)):
                        return False
                    if _check_values.get(cell) == current_block.get(cell):
                        return False
                return True

            first_kline = kline[0] if kline else {}
            last_kline = kline[-1] if kline else {}
            self._log_info(
                "开始轮询结果："
                f"股票代码={combination.get('stock_code', '')}，"
                f"股票名称={combination.get('stock_name', '')}，"
                f"随机分组={combination.get('random_group', '')}，"
                f"kline_key={kline_key}，"
                f"K线行数={len(kline)}，"
                f"日期范围={first_kline.get('stock_date', '')}~{last_kline.get('stock_date', '')}，"
                f"首条K线={first_kline}，末条K线={last_kline}"
            )

            def _attempt(_attempt_index):
                all_num = 0
                for google_sheet in self.google_sheets:
                    layout = sheet_layouts[google_sheet.spreadsheet_id]
                    output_range = layout["output_range"]
                    k_column = layout["output_column_k"]
                    merged_return_range_a1 = f"{k_column}2:{k_column}{len(kline) + 1}"
                    _result = {}
                    batch_results = google_sheet.get_ranges([
                        output_range,
                        merged_return_range_a1,
                    ])

                    if _validate_check_values(batch_results, google_sheet.spreadsheet_id, layout):
                        _result.update(batch_results.get(output_range, {}))

                        try:
                            merged_return_range = batch_results.get(merged_return_range_a1, {})
                            _start_return = check_result({
                                position: value
                                for position, value in merged_return_range.items()
                                if position.startswith(k_column)
                            })
                            # 指数序列统一走 AG 列随机价（写入侧 item.stock_val，与表内
                            # Index Return 汇总及 V2 报告读取同源），不再取 AE 随机 close
                            _index_returns = calculate_index_returns_from_closes(
                                [{'close': row.get('stock_val')} for row in kline]
                            )
                        except Exception as e:
                            self._log_info(f"获取结果位置 {merged_return_range_a1} 时出错：{str(e)}")
                            self._log_info(f"_result：{_result} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                            break

                        _return_data = []
                        for i in range(len(kline)):
                            _return_data.append({
                                'date': kline[i].get('stock_date'),
                                'index_return': _index_returns[i],
                                'start_return': _start_return[f"{k_column}{i + 2}"]
                            })

                        metrics_payload = self.performance_analyzer.get_return_analysis_v1(_return_data)
                        _result['metrics_payload'] = metrics_payload
                        _result['_return_date'] = _return_data

                        results[f"{google_sheet.spreadsheet_id}__{google_sheet.title}"] = _result
                        all_num += 1
                    else:
                        self._log_warning(f"第 {_attempt_index + 1} 次检查执行状态... 未完成")
                        self._log_warning(f"第 {_attempt_index + 1} 次检查执行状态... 结果块:{batch_results.get(output_range, {})} 起始参数:{initial_results[google_sheet.spreadsheet_id]}")
                        break

                if all_num == len(self.google_sheets):
                    self._log_info("所有任务已完成")
                    return True, results
                return False, None

            # 定时检查是否完成；刷新/延时/取消/超时统一走 base 轮询骨架
            return self._poll_google_sheet_completion(_attempt, refresh_fn=set_googl_val)

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

    # ---- 结果载荷 ----

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
                "kline": combination.get("kline", []),
            },
        )
        first_value = next(iter(result.values()), None) if isinstance(result, dict) else None
        if isinstance(first_value, dict):
            result = first_value
        output_column, output_row = parse_range_start(
            combination.get("c1_1_output_range") or C1_1_DEFAULT_OUTPUT_RANGE
        )
        analyze_result = (result.get('metrics_payload') or {}).get('metrics', {})

        payload.update({
            "stock_code": combination.get("stock_code"),
            **build_c1_1_summary_fields(lambda offset: result.get(f"{output_column}{output_row + offset}", 0)),
            **build_analyze_fields(analyze_result),
        })
        return payload
