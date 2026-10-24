from app.utils.json_utils import dumps
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key
from io import BytesIO
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.constants.c_template_layout import (
    C3_METRIC_CELLS,
    C3_PARAM_CELL_MAP,
    C3_PARAM_NAMES,
    C5_EXPORT_METRIC_KEYS,
    C7_ROW_SHIFT,
)
from app.exceptions import ValidationError
from app.services.performance_analysis.projections import flatten_v1_metrics
from app.utils.c7_result_normalizer import normalize_c7_result_metrics
from app.utils.model_version import normalize_model_version, resolve_model_version


EXCEL_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MIMETYPE = "application/zip"

# 统一导出文件名规范：{基名}-{模型版本}-{K线起}-{K线止}-{导出时间}.{扩展名}
# 段间 `-`、段内 `_`；模型版本/区间缺失时整段省略；导出时间恒在。
EXPORT_FILENAME_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
# 基名+后缀总长上限（含扩展名），超长时截断基名，保护 Windows 路径长度。
EXPORT_FILENAME_MAX_LENGTH = 180

# C5 分组 sheet 只展示业务关注列；kline_range 仅作为拆 sheet 的分组依据，不展示在表格里。
C5_EXPORT_COLUMNS = [
    "xm",
    "ml",
    "ReturnBeats_0",
    "ddBeats_0",
    "AnnualizedBeats_0",
    "ReturnBeats",
    "ddBeats",
    "Return",
    "Annualized",
    "Max DD%",
    "Index Return",
    "Annualized",
    "Index max dd",
    "单位理论杠杆率收益",
    "单位实际杠杆率收益",
    "模型年化标准差",
    "指数年化标准差",
    "指数夏普",
    "模型夏普",
]

# C5_EXPORT_METRIC_KEYS 来自 app/constants/c_template_layout 的 C4/C5 概念键派生；
# C5_PERCENT_METRIC_KEYS 是导出侧专用的百分数格式集合。
C5_PERCENT_METRIC_KEYS = frozenset(C5_EXPORT_METRIC_KEYS)

# 导出列尾追加列：普通导出=股票代码+结果ID；按股票代码导出=仅结果ID（股票代码已在文件名里）。
EXPORT_TAIL_COLUMNS = ["股票代码", "结果ID"]
EXPORT_TAIL_COLUMNS_BY_STOCK = ["结果ID"]


def export_tail_columns(by_stock: bool) -> list[str]:
    return EXPORT_TAIL_COLUMNS_BY_STOCK if by_stock else EXPORT_TAIL_COLUMNS


def export_tail_values(stock_code: str, result_id: Any, by_stock: bool) -> list[Any]:
    if by_stock:
        return [result_id]
    return [stock_code, result_id]

PERCENT_COLUMN_NAMES = {
    "ReturnBeats",
    "ddBeats",
    "ReturnBeats_0",
    "ddBeats_0",
    "AnnualizedBeats_0",
    "Return",
    "Annualized",
    "Max DD%",
    "Index Return",
    "Index max dd",
    "单位理论杠杆率收益",
    "单位实际杠杆率收益",
    "平均波动率",
}

FOUR_DECIMAL_COLUMN_NAMES = {
    "模型年化标准差",
    "指数年化标准差",
    "指数夏普",
    "模型夏普",
}

# 文本保真列：股票代码必须按字符串写入，否则前导零被数值化（002594 → 2594）。
TEXT_PRESERVING_COLUMN_NAMES = {"股票代码"}

# C3 导出列定义
C3_EXPORT_COLUMNS = [
    "top choices",
    "ywf top choices",
    "data start",
    "data end",
    *C3_PARAM_NAMES,
    "annualized%",
    "index%",
    "beats",
    "strat max dd%",
    "index max dd%",
    "beats_dd",
    "Fee total",
    "Fee annualize",
    "年换手率",
    "模型年化标准差",
    "指数年化标准差",
    "指数夏普",
    "模型夏普",
]

# 导出时 "beats_dd" 在表头显示为 "beats"（与 return beats 列同名，业务约定）
C3_HEADER_DISPLAY = {"beats_dd": "beats"}

C3_COLUMN_WIDTHS = {
    "top choices": 16,
    "ywf top choices": 16,
    "data start": 14,
    "data end": 14,
    "xm": 7,
    "tp1": 7,
    "nl": 7,
    "if": 7,
    "ywfs": 7,
    "ywb": 7,
    "annualized%": 14,
    "index%": 10,
    "beats": 10,
    "beats_dd": 10,
    "strat max dd%": 14,
    "index max dd%": 14,
    "Fee total": 12,
    "Fee annualize": 14,
    "年换手率": 12,
    "模型年化标准差": 16,
    "指数年化标准差": 16,
    "指数夏普": 11,
    "模型夏普": 11,
}

# C3 导出字段格式说明：
# 数据库存储的是小数（如 0.15），SQL 层已乘以 100 后存储（如 15.0）。
# 导出时直接显示为纯数字，不添加 "%" 后缀，不使用 Excel 百分比格式。

# 这些列的值已在 SQL 中乘以 100，导出时用 "0.00" 格式显示纯数字
C3_NUMBER_COLUMN_NAMES = {
    "annualized%",
    "index%",
    "beats",
    "beats_dd",
    "strat max dd%",
    "index max dd%",
    "Fee total",
    "Fee annualize",
    "年换手率",
}

C3_FOUR_DECIMAL_COLUMN_NAMES = {
    "模型年化标准差",
    "指数年化标准差",
    "指数夏普",
    "模型夏普",
}

C5_COLUMN_WIDTHS = {
    "xm": 7,
    "ml": 7,
    "ReturnBeats": 12,
    "ddBeats": 10,
    "ReturnBeats_0": 14,
    "ddBeats_0": 12,
    "AnnualizedBeats_0": 18,
    "Return": 10,
    "Annualized": 12,
    "Max DD%": 10,
    "Index Return": 12,
    "Index max dd": 12,
    "单位理论杠杆率收益": 18,
    "单位实际杠杆率收益": 18,
    "模型年化标准差": 16,
    "指数年化标准差": 16,
    "指数夏普": 11,
    "模型夏普": 11,
}

# C1.1 导出列 = C5 导出列在"单位实际杠杆率收益"右侧追加"平均波动率"（结果块 F23）；
# ml 列保留表头但 C1.1 无 B1 语义，内容留空。
C1_1_EXPORT_COLUMNS = [*C5_EXPORT_COLUMNS]
C1_1_AVG_VOLATILITY_COLUMN_INDEX = C1_1_EXPORT_COLUMNS.index("单位实际杠杆率收益") + 1
C1_1_EXPORT_COLUMNS.insert(C1_1_AVG_VOLATILITY_COLUMN_INDEX, "平均波动率")


@dataclass(frozen=True)
class GeneratedExport:
    filename: str
    mimetype: str
    workbook: Workbook


@dataclass(frozen=True)
class GeneratedArchive:
    filename: str
    mimetype: str
    buffer: BytesIO


@dataclass(frozen=True)
class WorksheetData:
    name: str
    header: list[Any]
    rows: list[list[Any]]


@dataclass(frozen=True)
class C5ResultGroup:
    """C5 原始 TaskResult 的中间结构，先归一化再展开模型行。"""

    step_index: Any
    success: bool
    stock_code: str
    kline_range: str
    xm: Any
    ml: Any
    task_id: str
    timestamp: str
    error_message: str
    models: list[dict[str, Any]]
    result_id: Any = ""


@dataclass(frozen=True)
class C5ExportRecord:
    group: C5ResultGroup
    row: list[Any]


def normalize_filename_date(value: Any) -> str:
    """日期归一为 YYYYMMDD 文件名段；无法识别返回空串。"""

    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    if not text:
        return ""
    head = re.split(r"[ T]", text)[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(head, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return ""


def build_export_filename(
    base: Any,
    model_version: Any = "",
    kline_start: Any = "",
    kline_end: Any = "",
    extension: str = "xlsx",
    *,
    now: datetime | None = None,
) -> str:
    """按统一规范组装导出文件名。

    模型版本/K线区间缺失时整段省略，区间段成对出现（起止归一后按时间升序）；
    导出时间段恒在；总长超上限时截断基名。
    """

    stamp = (now or datetime.now()).strftime(EXPORT_FILENAME_TIMESTAMP_FORMAT)
    start_text = normalize_filename_date(kline_start)
    end_text = normalize_filename_date(kline_end)
    if start_text and end_text and start_text > end_text:
        start_text, end_text = end_text, start_text
    if not (start_text and end_text):
        start_text = end_text = ""
    version_text = str(model_version or "").strip()
    segments = [
        sanitize_export_filename(base),
        sanitize_export_filename(version_text) if version_text else "",
        start_text,
        end_text,
        stamp,
    ]
    filename = "-".join(segment for segment in segments if segment)
    if len(filename) > EXPORT_FILENAME_MAX_LENGTH:
        overflow = len(filename) - EXPORT_FILENAME_MAX_LENGTH
        kept_base = segments[0][: max(len(segments[0]) - overflow, 1)].rstrip("-_ .")
        filename = "-".join([kept_base, *(segment for segment in segments[1:] if segment)])
    return f"{filename}.{extension}" if extension else filename


def kline_bounds_from_params(params: dict[str, Any]) -> tuple[str, str]:
    """从参数 kline 明细取真实首末交易日（原样字符串）；缺失返回 ("", "")。"""

    kline = params.get("kline") if isinstance(params, dict) else None
    if not isinstance(kline, list):
        return "", ""
    dated = sorted(
        str(row.get("stock_date") or "")
        for row in kline
        if isinstance(row, dict) and row.get("stock_date")
    )
    if not dated:
        return "", ""
    return dated[0], dated[-1]


def kline_bounds_from_results(results: list[dict[str, Any]]) -> tuple[str, str]:
    """结果集整体 K 线包络（所有组合真实首末交易日的 min/max）；缺失返回 ("", "")。"""

    bounds = [
        kline_bounds_from_params(
            item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        )
        for item in results or []
    ]
    starts = sorted(bound[0] for bound in bounds if bound[0])
    ends = sorted(bound[1] for bound in bounds if bound[1])
    if not starts or not ends:
        return "", ""
    return starts[0], ends[-1]


def model_version_from_config(config: Any) -> str:
    """任务配置里的模型版本：sheets[0].model_version 优先，回落根级 model_version（历史平铺形态）。"""

    if not isinstance(config, dict):
        return ""
    sheets = config.get("sheets")
    first_sheet = (
        sheets[0]
        if isinstance(sheets, list) and sheets and isinstance(sheets[0], dict)
        else {}
    )
    version = normalize_model_version(first_sheet.get("model_version"))
    if version:
        return version
    return normalize_model_version(config.get("model_version")) or ""


def model_version_from_results(results: list[dict[str, Any]], task: Any = None) -> str:
    """结果组合打标的模型版本：唯一则返回，混版本/未知返回空串（文件名省略该段）。

    历史 taskId 无打标时回落任务配置（sheets[]/根级 model_version）与任务类型推断。
    """

    versions = {
        normalized
        for item in results or []
        if isinstance(item.get("parameters"), dict)
        for normalized in (normalize_model_version(item["parameters"].get("model_version")),)
        if normalized
    }
    if len(versions) == 1:
        return next(iter(versions))
    if versions or task is None:
        return ""
    config = getattr(task, "config", None)
    fallback = model_version_from_config(config)
    if fallback:
        return fallback
    sheets = config.get("sheets") if isinstance(config, dict) and isinstance(config.get("sheets"), list) else []
    first_sheet = sheets[0] if sheets and isinstance(sheets[0], dict) else {}
    return resolve_model_version(_task_type(task), first_sheet)


def _excel_export(
    task: Any,
    worksheets: list[WorksheetData],
    results: list[dict[str, Any]] | None = None,
) -> GeneratedExport:
    """C7/C5/C3 共用的 Excel 组装：文件名走统一命名规范，worksheet 由各类型给定。"""
    kline_start, kline_end = kline_bounds_from_results(results or [])
    return GeneratedExport(
        filename=build_export_filename(
            _task_name(task),
            model_version=model_version_from_results(results or [], task),
            kline_start=kline_start,
            kline_end=kline_end,
        ),
        mimetype=EXCEL_MIMETYPE,
        workbook=build_workbook(worksheets),
    )


def _generic_export(task: Any, results: list[dict[str, Any]]) -> GeneratedExport:
    """通用兜底导出：未定制的任务类型也能下载原始结果。"""
    header = [
        "id",
        "task_id",
        "step_index",
        "success",
        "timestamp",
        "parameters",
        "result",
        "error_message",
    ]
    rows = [
        [
            item.get("id", ""),
            item.get("task_id", ""),
            item.get("step_index", ""),
            "success" if item.get("success") else "failed",
            format_time(item.get("timestamp")),
            json_cell(item.get("parameters")),
            json_cell(item.get("result")),
            item.get("error_message") or "",
        ]
        for item in results
    ]
    return _excel_export(
        task,
        [WorksheetData(name="任务结果", header=header, rows=rows)],
        results=results,
    )


def build_task_export(task: Any, results: list[dict[str, Any]], by_stock: bool = False) -> GeneratedExport:
    """导出统一入口；路由层负责查任务和结果，本服务只做格式转换。

    - C7/C1.1：展开每个模型为一行（先归一化），按 K 线范围拆分 worksheet；
      C1.1 用自身列布局（单位实际杠杆率收益右侧加平均波动率），其余走 C5 列；
    - C5：展开每个模型为一行，按 K 线范围拆分 worksheet；
    - C3（google_sheet/google_sheet_c3）：每个参数组合一行，按 K 线范围拆分 worksheet；
    - 其余任务类型走通用兜底。
    - by_stock=True（按股票代码分组导出）时列尾只追加结果ID，不重复输出股票代码。
    """
    task_type = _task_type(task)
    if task_type in ("google_sheet_c7", "google_sheet_c1_1"):
        normalized = (
            normalize_c1_1_export_results(results)
            if task_type == "google_sheet_c1_1"
            else normalize_c7_export_results(results)
        )
        if task_type == "google_sheet_c1_1":
            return _excel_export(task, build_c1_1_worksheets(normalized, by_stock), results)
        return _excel_export(task, build_c5_worksheets(normalized, by_stock), results)
    if task_type == "google_sheet_c5":
        return _excel_export(task, build_c5_worksheets(results, by_stock), results)
    if task_type in ("google_sheet", "google_sheet_c3"):
        return _excel_export(task, build_c3_worksheets(results, by_stock), results)
    return _generic_export(task, results)


def build_c7_stock_code_export_archive(task: Any, results: list[dict[str, Any]]) -> GeneratedArchive:
    """按股票代码拆分 C7/C1.1 结果，并将现有 Excel 导出格式打包为 ZIP。"""

    if _task_type(task) not in ("google_sheet_c7", "google_sheet_c1_1"):
        raise ValidationError("按股票代码导出仅支持 C7/C1.1 任务")
    if not results:
        raise ValidationError("任务暂无可导出结果")

    grouped_results: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        parameters = item.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}
        stock_code = str(parameters.get("stock_code") or "未命名股票").strip() or "未命名股票"
        grouped_results.setdefault(stock_code, []).append(item)

    archive_buffer = BytesIO()
    used_filenames: set[str] = set()
    task_name = sanitize_export_filename(_task_name(task))
    # 混版本（C7 多表各选版本）时版本段省略；zip 外层按规范不带区间段。
    model_version = model_version_from_results(results, task)
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        for stock_code in sorted(grouped_results, reverse=True):
            stock_results = grouped_results[stock_code]
            workbook_export = build_task_export(task, stock_results, by_stock=True)
            workbook_buffer = BytesIO()
            workbook_export.workbook.save(workbook_buffer)

            stock_start, stock_end = kline_bounds_from_results(stock_results)
            filename_base = sanitize_export_filename(
                build_export_filename(
                    f"{task_name}_{stock_code}",
                    model_version=model_version_from_results(stock_results, task) or model_version,
                    kline_start=stock_start,
                    kline_end=stock_end,
                    extension="",
                )
            )
            filename = f"{filename_base}.xlsx"
            suffix = 2
            while filename in used_filenames:
                filename = f"{filename_base}_{suffix}.xlsx"
                suffix += 1
            used_filenames.add(filename)
            archive.writestr(filename, workbook_buffer.getvalue())

    archive_buffer.seek(0)
    return GeneratedArchive(
        filename=build_export_filename(
            f"{task_name}_按股票代码导出",
            model_version=model_version,
            extension="zip",
        ),
        mimetype=ZIP_MIMETYPE,
        buffer=archive_buffer,
    )


def build_c5_records(
    results: list[dict[str, Any]],
    by_stock: bool = False,
    *,
    empty_model_row: Callable[[C5ResultGroup, bool], list[Any]] | None = None,
    model_row: Callable[[C5ResultGroup, dict[str, Any], bool], list[Any]] | None = None,
) -> list[C5ExportRecord]:
    """生成带分组上下文的导出行；上下文用于排序和拆 sheet，不写入最终 Excel。

    行构建器可替换：C1.1 复用分组/排序骨架，仅替换行投影（见 build_c1_1_worksheets）。
    """

    empty_row_builder = empty_model_row or c5_empty_model_row
    row_builder = model_row or c5_model_row

    records = []
    for group in build_c5_groups(results):
        if not group.models:
            records.append(C5ExportRecord(group=group, row=empty_row_builder(group, by_stock)))
            continue

        for model in group.models:
            records.append(C5ExportRecord(group=group, row=row_builder(group, model, by_stock)))

    return sort_c5_records(records)


def build_c5_groups(results: list[dict[str, Any]]) -> list[C5ResultGroup]:
    """先把数据库里的松散 JSON 结果归一化，后续展开行时不用反复判空。"""

    groups = []
    for item in results:
        params = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        groups.append(
            C5ResultGroup(
                step_index=item.get("step_index"),
                success=bool(item.get("success")),
                stock_code=str(params.get("stock_code") or ""),
                kline_range=kline_range_from_params(params),
                xm=params.get("A1", ""),
                ml=params.get("B1", ""),
                task_id=str(item.get("task_id") or ""),
                timestamp=format_time(item.get("timestamp")),
                error_message=str(item.get("error_message") or ""),
                models=[build_c5_model(model_key, metrics) for model_key, metrics in result.items()],
                result_id=item.get("id", ""),
            )
        )
    return groups


def build_c5_model(model_key: Any, metrics: Any) -> dict[str, Any]:
    raw_metrics = metrics if isinstance(metrics, dict) else {}
    key_text = str(model_key)
    key_parts = key_text.split("__")
    metrics_payload = raw_metrics.get("metrics_payload")
    v1_metrics = (
        metrics_payload.get("metrics")
        if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("metrics"), dict)
        else {}
    )
    flat = flatten_v1_metrics(v1_metrics)
    start_legacy_metrics = {
        "annual_std_dev": flat.get("start_annual_std_dev") or flat.get("start_monthly_std_dev", ""),
        "sharpe_ratio": flat.get("start_sharpe_ratio", ""),
    }
    index_legacy_metrics = {
        "annual_std_dev": flat.get("index_annual_std_dev") or flat.get("index_monthly_std_dev", ""),
        "sharpe_ratio": flat.get("index_sharpe_ratio", ""),
    }

    return {
        "model_key": key_text,
        "model_title": "__".join(key_parts[1:]) if len(key_parts) > 1 else key_text,
        "metrics": raw_metrics,
        "start_legacy_metrics": start_legacy_metrics,
        "index_legacy_metrics": index_legacy_metrics,
        "start_sharpe": start_legacy_metrics.get("sharpe_ratio", ""),
        "index_sharpe": index_legacy_metrics.get("sharpe_ratio", ""),
    }


def c5_empty_model_row(group: C5ResultGroup, by_stock: bool = False) -> list[Any]:
    return [
        group.xm if group.xm is not None else "",
        group.ml if group.ml is not None else "",
        *([""] * (len(C5_EXPORT_COLUMNS) - 2)),
        *export_tail_values(group.stock_code, group.result_id, by_stock),
    ]


def c5_model_row(group: C5ResultGroup, model: dict[str, Any], by_stock: bool = False) -> list[Any]:
    metrics = model["metrics"]
    start_legacy_metrics = model["start_legacy_metrics"]
    index_legacy_metrics = model["index_legacy_metrics"]
    return_beats_0 = c5_percent_difference(metrics.get("D2"), metrics.get("D5"))
    dd_beats_0 = c5_percent_difference(metrics.get("D4"), metrics.get("D7"))
    annualized_beats_0 = c5_percent_difference(metrics.get("D3"), metrics.get("D6"))

    return [
        group.xm if group.xm is not None else "",
        group.ml if group.ml is not None else "",
        return_beats_0,
        dd_beats_0,
        annualized_beats_0,
        c5_metric_value(metrics, "D11"),
        c5_metric_value(metrics, "D12"),
        *[c5_metric_value(metrics, key) for key in C5_EXPORT_METRIC_KEYS[2:]],
        start_legacy_metrics.get("annual_std_dev", ""),
        index_legacy_metrics.get("annual_std_dev", ""),
        model.get("index_sharpe", ""),
        model.get("start_sharpe", ""),
        *export_tail_values(group.stock_code, group.result_id, by_stock),
    ]


def c5_metric_value(metrics: dict[str, Any], key: str) -> Any:
    """结果表已计算 D11/D12，导出直接保留原始指标。"""

    return metrics.get(key, "")


def c5_percent_difference(left: Any, right: Any) -> Any:
    """按导出百分比规则计算两项指标差值。"""

    left_value = excel_cell(left, "Return")
    right_value = excel_cell(right, "Return")
    return _safe_subtract(left_value, right_value)


def normalize_c7_export_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 C7 的 D8:D26 结果键映射成 C5 导出函数使用的 D2:D20 键。"""

    normalized_results = []
    for item in results:
        result = item.get("result")
        if not isinstance(result, dict):
            normalized_results.append(item)
            continue

        parameters = item.get("parameters") or {}
        if parameters.get("model_version") == "c7_0_3":
            normalized_results.append(item)
            continue

        normalized_models = {}
        for model_key, metrics in result.items():
            normalized_models[model_key] = normalize_c7_model_metrics(metrics)

        normalized_item = dict(item)
        normalized_item["result"] = normalized_models
        normalized_results.append(normalized_item)
    return normalized_results


def normalize_c7_model_metrics(metrics: Any) -> Any:
    if not isinstance(metrics, dict):
        return metrics

    # 旧数据若已经是 D2:D20 结构，不做二次平移，避免把 D8 fee_total 当成 Return。
    has_c7_shifted_keys = (
        any(f"D{index}" in metrics for index in range(21, 27))
        or ("D2" not in metrics and any(f"D{index}" in metrics for index in range(8, 21)))
    )
    if not has_c7_shifted_keys:
        return metrics

    source_metrics = normalize_c7_result_metrics(metrics)
    normalized = dict(source_metrics)
    for c5_index in range(2, 21):
        c7_key = f"D{c5_index + C7_ROW_SHIFT}"
        if c7_key in source_metrics:
            normalized_key = f"D{c5_index}"
            value = source_metrics[c7_key]
            if normalized_key in C5_PERCENT_METRIC_KEYS and isinstance(value, str) and "%" not in value:
                value = f"{value}%"
            normalized[normalized_key] = value
    return normalized


# C1.1 结果块（默认 F2:F26，行序见 result_payload.C1_1_RESULT_FIELD_SPECS）→ C5 导出 D 键的行偏移。
# 单位理论杠杆率收益（D17）按业务约定用 F16 最大杠杆率补充（非百分数，原样透传）；
# 单位实际杠杆率收益（D20）无对应单元格，留空。
C1_1_TO_C5_METRIC_OFFSETS = {
    "D2": 2,    # return_rate
    "D3": 3,    # annualized_rate
    "D4": 4,    # maxdd
    "D5": 6,    # index_rate
    "D6": 7,    # index_annualized_rate
    "D7": 8,    # max_index_dd
    "D11": 10,  # return_beats
    "D12": 11,  # dd_beats
}
C1_1_MAX_LEVERAGE_OFFSET = 14    # F16 最大杠杆率 → D17 单位理论杠杆率收益列
C1_1_AVG_VOLATILITY_OFFSET = 21  # F23 平均波动率 → 独立导出列
C1_1_REF_XM_OFFSET = 22
C1_1_DEFAULT_RANGE_ANCHOR = ("F", 2)


def _with_percent_suffix(value: Any) -> Any:
    """结果块百分数裸数字补 "%"；已带 "%" 或非字符串原样返回。"""
    if isinstance(value, str) and value.strip() and "%" not in value:
        return f"{value}%"
    return value


def _c1_1_range_anchor(output_range: Any) -> tuple[str, int]:
    """解析 "F2:F26" 式结果块起点；非法输入回退默认 F2。"""
    start = str(output_range or "").split(":")[0].strip().upper()
    match = re.fullmatch(r"([A-Z]+)(\d+)", start)
    if not match:
        return C1_1_DEFAULT_RANGE_ANCHOR
    return match.group(1), int(match.group(2))


def normalize_c1_1_export_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 C1.1 的结果块单元格键映射成 C5 导出函数使用的 D2:D20 键。

    xm/ml 两列 C1.1 参数里没有 A1/B1 语义：xm 取结果块 ref_xm，ml 列保留表头但内容留空。
    D17 用结果块最大杠杆率（F16）补充；平均波动率（F23）以 "avg_volatility" 键透出，
    由 C1.1 行构建器插入单位实际杠杆率收益右侧。
    """

    normalized_results = []
    for item in results:
        result = item.get("result")
        if not isinstance(result, dict):
            normalized_results.append(item)
            continue

        parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        output_column, output_row = _c1_1_range_anchor(parameters.get("c1_1_output_range"))

        normalized_models = {}
        ref_xm = ""
        for model_key, metrics in result.items():
            if not isinstance(metrics, dict):
                normalized_models[model_key] = metrics
                continue
            normalized = dict(metrics)
            for c5_key, offset in C1_1_TO_C5_METRIC_OFFSETS.items():
                normalized[c5_key] = _with_percent_suffix(
                    metrics.get(f"{output_column}{output_row + offset}", "")
                )
            normalized["D17"] = metrics.get(f"{output_column}{output_row + C1_1_MAX_LEVERAGE_OFFSET}", "")
            normalized["avg_volatility"] = _with_percent_suffix(
                metrics.get(f"{output_column}{output_row + C1_1_AVG_VOLATILITY_OFFSET}", "")
            )
            if not ref_xm:
                ref_xm = metrics.get(f"{output_column}{output_row + C1_1_REF_XM_OFFSET}", "")
            normalized_models[model_key] = normalized

        normalized_item = dict(item)
        normalized_item["result"] = normalized_models
        normalized_params = dict(parameters)
        normalized_params["A1"] = ref_xm
        normalized_item["parameters"] = normalized_params
        normalized_results.append(normalized_item)
    return normalized_results


def sort_c5_records(records: list[C5ExportRecord]) -> list[C5ExportRecord]:
    """按股票和 K 线区间稳定排列，sheet 内排序在分组后单独处理。"""

    def compare(left: C5ExportRecord, right: C5ExportRecord) -> int:
        comparisons = [
            compare_desc(left.group.stock_code, right.group.stock_code),
            compare_desc(parse_range_end(left.group.kline_range), parse_range_end(right.group.kline_range)),
            compare_desc(parse_range_start(left.group.kline_range), parse_range_start(right.group.kline_range)),
        ]
        return next((value for value in comparisons if value), 0)

    return sorted(records, key=cmp_to_key(compare))


def build_c5_worksheets(results: list[dict[str, Any]], by_stock: bool = False) -> list[WorksheetData]:
    """按 kline_range 拆分 worksheet；同一个 K 线范围的模型行放在同一个 sheet。"""

    records = build_c5_records(results, by_stock)
    header = C5_EXPORT_COLUMNS + export_tail_columns(by_stock)
    if not records:
        return [WorksheetData(name="无K线区间", header=header, rows=[])]

    grouped_rows = group_c5_records_by_kline_range(records)

    return [
        WorksheetData(name=group_name, header=header, rows=group_rows)
        for group_name, group_rows in grouped_rows.items()
    ]


def c1_1_empty_model_row(group: C5ResultGroup, by_stock: bool = False) -> list[Any]:
    row = c5_empty_model_row(group, by_stock)
    row.insert(C1_1_AVG_VOLATILITY_COLUMN_INDEX, "")
    return row


def c1_1_model_row(group: C5ResultGroup, model: dict[str, Any], by_stock: bool = False) -> list[Any]:
    row = c5_model_row(group, model, by_stock)
    row.insert(C1_1_AVG_VOLATILITY_COLUMN_INDEX, model["metrics"].get("avg_volatility") or "")
    return row


def build_c1_1_worksheets(results: list[dict[str, Any]], by_stock: bool = False) -> list[WorksheetData]:
    """C1.1 列布局：在 C5 行基础上于单位实际杠杆率收益右侧插入平均波动率（F23）。"""

    records = build_c5_records(
        results,
        by_stock,
        empty_model_row=c1_1_empty_model_row,
        model_row=c1_1_model_row,
    )
    header = C1_1_EXPORT_COLUMNS + export_tail_columns(by_stock)
    if not records:
        return [WorksheetData(name="无K线区间", header=header, rows=[])]

    grouped_rows = group_c5_records_by_kline_range(records)

    return [
        WorksheetData(name=group_name, header=header, rows=group_rows)
        for group_name, group_rows in grouped_rows.items()
    ]


def group_c5_records_by_kline_range(records: list[C5ExportRecord]) -> "OrderedDict[str, list[list[Any]]]":
    grouped_records = OrderedDict()
    for record in records:
        key = str(record.group.kline_range or "无K线区间")
        grouped_records.setdefault(key, []).append(record)
    return OrderedDict(
        (key, [record.row for record in sort_c5_sheet_records(group_records)])
        for key, group_records in grouped_records.items()
    )


def sort_c5_sheet_records(records: list[C5ExportRecord]) -> list[C5ExportRecord]:
    """每个分组 sheet 内：xm 为空的置顶；两段都按 ReturnBeats 降序。"""

    return_beats_col = C5_EXPORT_COLUMNS.index("ReturnBeats")

    def compare(left: C5ExportRecord, right: C5ExportRecord) -> int:
        comparisons = [
            compare_asc(is_non_empty_xm(left.group.xm), is_non_empty_xm(right.group.xm)),
            compare_desc(parse_percent(left.row[return_beats_col]), parse_percent(right.row[return_beats_col])),
        ]
        return next((value for value in comparisons if value), 0)

    return sorted(records, key=cmp_to_key(compare))


def kline_range_from_params(params: dict[str, Any]) -> str:
    """从参数里的 kline 明细推导展示区间；缺失时统一归到 '-' 分组。"""

    start, end = kline_bounds_from_params(params)
    if not start:
        return "-"
    return f"{start} ~ {end}"


def build_workbook(worksheets: list[WorksheetData]) -> Workbook:
    """把通用 WorksheetData 写入 openpyxl Workbook，并统一应用表格样式。"""

    workbook = Workbook()
    workbook.remove(workbook.active)

    if not worksheets:
        worksheets = [WorksheetData(name="导出结果", header=["暂无可导出的结果"], rows=[])]

    used_names: set[str] = set()
    for index, worksheet_data in enumerate(worksheets, start=1):
        sheet = workbook.create_sheet(unique_sheet_name(worksheet_data.name, f"分组{index}", used_names))
        sheet.append([excel_cell(value) for value in worksheet_data.header])
        column_names = [str(value or "") for value in worksheet_data.header]
        for row in worksheet_data.rows:
            sheet.append([
                excel_cell(value, column_names[column_index] if column_index < len(column_names) else "")
                for column_index, value in enumerate(row)
            ])
        style_table_sheet(sheet)

    return workbook


def style_table_sheet(sheet: Any) -> None:
    """统一导出样式：冻结表头、居中显示、设置边框和自适应列宽。

    优化策略：
    - 预计算每列的数字格式，避免逐单元格重复查表头
    - 样式对象在列级别复用，减少不必要的条件判断
    - 列宽只对有预定义宽度的列查表，其余列一次扫描取最大宽度
    """

    # ── 预创建复用样式对象 ──
    header_fill = PatternFill("solid", fgColor="F7E1A1")
    header_font = Font(name="Microsoft YaHei", size=10, bold=True)
    body_font = Font(name="Microsoft YaHei", size=10)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
    border = Border(
        left=Side(style="thin", color="D0D0D0"),
        right=Side(style="thin", color="D0D0D0"),
        top=Side(style="thin", color="D0D0D0"),
        bottom=Side(style="thin", color="D0D0D0"),
    )

    sheet.freeze_panes = "A2"

    max_row = sheet.max_row
    max_col = sheet.max_column

    # ── 预计算每列的数字格式（一次查表，全列复用）──
    col_format: dict[int, str] = {}
    for col_idx in range(1, max_col + 1):
        col_name = str(sheet.cell(row=1, column=col_idx).value or "")
        if col_name in PERCENT_COLUMN_NAMES:
            col_format[col_idx] = "0.00%"
        elif col_name in FOUR_DECIMAL_COLUMN_NAMES or col_name in C3_FOUR_DECIMAL_COLUMN_NAMES:
            col_format[col_idx] = "0.0000"
        elif col_name in C3_NUMBER_COLUMN_NAMES:
            col_format[col_idx] = "0.00"

    # ── 逐行应用样式（header 单独处理，body 统一样式 + 列格式）──
    for row_idx in range(1, max_row + 1):
        sheet.row_dimensions[row_idx].height = 18
        is_header = row_idx == 1
        for col_idx in range(1, max_col + 1):
            cell = sheet.cell(row=row_idx, column=col_idx)
            cell.border = border
            if is_header:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment
            else:
                cell.font = body_font
                cell.alignment = body_alignment
                fmt = col_format.get(col_idx)
                if fmt and isinstance(cell.value, (int, float)):
                    cell.number_format = fmt

    # ── 列宽：预定义宽度优先，其余一次扫描计算 ──
    for col_idx in range(1, max_col + 1):
        letter = get_column_letter(col_idx)
        header = str(sheet.cell(row=1, column=col_idx).value or "")
        predefined = C5_COLUMN_WIDTHS.get(header) or C3_COLUMN_WIDTHS.get(header)
        if predefined:
            sheet.column_dimensions[letter].width = predefined
        else:
            # 只在没有预定义宽度时扫描内容
            max_w = 0
            for row_idx in range(1, max_row + 1):
                max_w = max(max_w, display_width(sheet.cell(row=row_idx, column=col_idx).value))
            sheet.column_dimensions[letter].width = min(max(max_w + 2, 8), 40)


def display_width(value: Any) -> int:
    text = str(value or "")
    width = 0
    for char in text:
        width += 2 if ord(char) > 127 else 1
    return width


def excel_cell(value: Any, column_name: str = "") -> Any:
    """openpyxl 不能写入 dict/list，复杂对象统一转成 JSON 字符串。"""

    if value is None:
        return ""
    if column_name in TEXT_PRESERVING_COLUMN_NAMES:
        return str(value).strip()
    if isinstance(value, (int, float, bool, datetime)):
        return value
    if isinstance(value, str):
        if column_name in PERCENT_COLUMN_NAMES:
            percent_value = parse_percent_cell(value)
            return "" if percent_value is None else percent_value
        numeric_value = parse_numeric_cell(value)
        return value if numeric_value is None else numeric_value
    return json_cell(value)


def parse_percent_cell(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("%"):
        number = parse_numeric_cell(text[:-1])
        return None if number is None else number / 100
    return parse_numeric_cell(text)


def parse_numeric_cell(value: str) -> float | int | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("%"):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number:
        return None
    return int(number) if number.is_integer() else number


def json_cell(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    return dumps(value, ensure_ascii=False, default=str)


def format_time(value: Any) -> str:
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value)
        else:
            return str(value)
    except (TypeError, ValueError):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_export_filename(name: Any, fallback: str = "task_export") -> str:
    safe_name = "".join(char if char not in '\\/:*?"<>|' else "_" for char in str(name or "")).strip()
    return safe_name or fallback


def unique_sheet_name(label: Any, fallback: str, used_names: set[str]) -> str:
    """Excel sheet 名最多 31 个字符，且同一个 workbook 内必须唯一。"""

    base_name = sanitize_sheet_name(label, fallback)
    sheet_name = base_name
    suffix = 1
    while sheet_name in used_names:
        suffix += 1
        suffix_text = f"_{suffix}"
        sheet_name = f"{base_name[:31 - len(suffix_text)]}{suffix_text}"
    used_names.add(sheet_name)
    return sheet_name


def sanitize_sheet_name(label: Any, fallback: str) -> str:
    name = str(label or "").strip() or fallback
    name = re.sub(r"[\[\]:*?/\\]", "_", name)
    name = re.sub(r"\s+", " ", name).strip("' ")
    return (name or fallback)[:31]


def parse_range_end(value: Any) -> float:
    parts = str(value or "").split("~")
    return parse_datetime_timestamp(parts[1].strip()) if len(parts) >= 2 else float("-inf")


def parse_range_start(value: Any) -> float:
    parts = str(value or "").split("~")
    return parse_datetime_timestamp(parts[0].strip()) if parts else float("-inf")


def parse_datetime_timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


def parse_percent(value: Any) -> float:
    number = parse_numeric_cell(str(value).replace("%", ""))
    return number if number is not None else float("-inf")


def normalize_xm(value: Any) -> str:
    text = str(value or "").strip()
    return "" if not text or text == "0" else text


def is_non_empty_xm(value: Any) -> bool:
    return bool(normalize_xm(value))


def compare_desc(left: Any, right: Any) -> int:
    if left == right:
        return 0
    return -1 if left > right else 1


def _safe_float(value: Any) -> float:
    """安全转换为 float，无效值返回负无穷以保证排序时始终排在末尾。"""
    if value is None or value == "":
        return float("-inf")
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("-inf")


def compare_asc(left: Any, right: Any) -> int:
    if left == right:
        return 0
    return -1 if left < right else 1


def _task_type(task: Any) -> str:
    return str(getattr(task, "task_type", "") or "").lower()


# ---------------------------------------------------------------------------
# C3 导出支持
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class C3ResultGroup:
    """C3 原始 TaskResult 的中间结构。"""

    step_index: Any
    success: bool
    stock_code: str
    kline_range: str
    kline_start: str
    kline_end: str
    params: list[Any]
    task_id: str
    timestamp: str
    error_message: str
    result: dict[str, Any]
    task_name: str = ""  # 批量合并导出时用于跨任务排序
    result_id: Any = ""


@dataclass(frozen=True)
class C3ExportRecord:
    group: C3ResultGroup
    row: list[Any]


def build_c3_groups(results: list[dict[str, Any]]) -> list[C3ResultGroup]:
    groups = []
    for item in results:
        params = item.get("parameters")
        if not isinstance(params, list):
            params = []

        result = item.get("result") if isinstance(item.get("result"), dict) else {}

        # kline 数据追加在参数列表末尾（可能是 dict 或 list）
        kline_data = params[-1] if params and isinstance(params[-1], (dict, list)) else None
        numeric_params = params[:-1] if kline_data is not None else params

        kline_range = "-"
        kline_start = ""
        kline_end = ""
        if isinstance(kline_data, dict) and kline_data.get("stock_date"):
            kline_start = str(kline_data.get("stock_date", ""))
            kline_end = kline_start
            kline_range = kline_start
        elif isinstance(kline_data, list):
            dated_rows = [r for r in kline_data if isinstance(r, dict) and r.get("stock_date")]
            if dated_rows:
                dated_rows.sort(key=lambda r: str(r.get("stock_date") or ""))
                kline_start = str(dated_rows[0].get("stock_date", ""))
                kline_end = str(dated_rows[-1].get("stock_date", ""))
                kline_range = f"{kline_start} ~ {kline_end}"

        groups.append(
            C3ResultGroup(
                step_index=item.get("step_index"),
                success=bool(item.get("success")),
                stock_code=str(result.get("stock_code") or ""),
                kline_range=kline_range,
                kline_start=kline_start,
                kline_end=kline_end,
                params=numeric_params,
                task_id=str(item.get("task_id") or ""),
                timestamp=format_time(item.get("timestamp")),
                error_message=str(item.get("error_message") or ""),
                result=result,
                task_name=str(item.get("task_name") or ""),
                result_id=item.get("id", ""),
            )
        )
    return groups


def build_c3_records(results: list[dict[str, Any]], by_stock: bool = False) -> list[C3ExportRecord]:
    records = []
    for group in build_c3_groups(results):
        records.append(C3ExportRecord(group=group, row=c3_result_row(group, by_stock)))
    return sort_c3_records(records)


def _c3_cell_value(result: dict[str, Any], cell_ref: str, named_key: str = "") -> Any:
    """从 C3 result dict 中读取值：优先单元格引用，回退到命名键。"""
    value = result.get(cell_ref, "")
    if value == "" and named_key:
        value = result.get(named_key, "")
    return value


def _safe_subtract(a: Any, b: Any) -> Any:
    """安全计算 a - b，任意一方非数值时返回空字符串。"""
    try:
        a_num = float(a) if a != "" and a is not None else None
        b_num = float(b) if b != "" and b is not None else None
        if a_num is None or b_num is None:
            return ""
        return a_num - b_num
    except (ValueError, TypeError):
        return ""


def _safe_multiply_100(value: Any) -> Any:
    """安全地将值乘以 100，非数值返回空字符串。"""
    if value is None or value == "":
        return ""
    try:
        return float(value) * 100
    except (ValueError, TypeError):
        return ""


def c3_result_row(group: C3ResultGroup, by_stock: bool = False) -> list[Any]:
    result = group.result

    # ── 参数列（从单元格引用读取，与 _build_stock_param_result_payload 一致）──
    param_values = [_c3_cell_value(result, cell, name) for name, cell in C3_PARAM_CELL_MAP]

    # ── 指标列（从单元格引用读取，与 SQL 查询字段一一对应）──
    # 数据库存储原始小数（如 0.15），业务层 ×100 后展示为 15.00
    annualized_rate      = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["annualized_rate"], "annualized_rate"))
    index_annualized_rate = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["index_annualized_rate"], "index_annualized_rate"))
    maxdd                = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["max_drawdown"], "maxdd"))
    max_index_dd         = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["index_max_drawdown"], "max_index_dd"))
    fee_total            = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["fee_total"], "fee_total"))
    fee_annualized       = _safe_multiply_100(_c3_cell_value(result, C3_METRIC_CELLS["fee_annualized"], "fee_annualized"))
    year_rate            = _c3_cell_value(result, C3_METRIC_CELLS["turnover_rate"], "year_rate")  # 年换手率不乘100

    # beats（收益差）和 beats_dd（回撤差）基于已乘 100 的值计算
    return_beats = _safe_subtract(annualized_rate, index_annualized_rate)
    dd_beats     = _safe_subtract(maxdd, max_index_dd)

    # 年换手率：优先读取命名键，回退到 year_rate（I23）
    turnover_rate = result.get("turnover_rate") or year_rate

    # ── 绩效分析字段（从 metrics_payload.metrics 读取）──
    metrics_payload = result.get("metrics_payload")
    v1_metrics = (
        metrics_payload.get("metrics")
        if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("metrics"), dict)
        else {}
    )
    flat = flatten_v1_metrics(v1_metrics)
    start_monthly_std_dev = flat.get("start_monthly_std_dev", "")
    index_monthly_std_dev = flat.get("index_monthly_std_dev", "")
    index_sharpe_ratio    = flat.get("index_sharpe_ratio", "")
    start_sharpe_ratio    = flat.get("start_sharpe_ratio", "")

    return [
        "",  # top choices（暂不填数据）
        "",  # ywf top choices（暂不填数据）
        "",  # data start（暂不填数据）
        "",  # data end（暂不填数据）
        *param_values,                    # xm, tp1, nl, if, ywfs, ywb
        annualized_rate,                  # annualized%
        index_annualized_rate,            # index%
        return_beats,                     # beats (return)
        maxdd,                            # strat max dd%
        max_index_dd,                     # index max dd%
        dd_beats,                         # beats (dd)
        fee_total,                        # Fee total
        fee_annualized,                   # Fee annualize
        turnover_rate,                    # 年换手率
        start_monthly_std_dev,            # 模型年化标准差
        index_monthly_std_dev,            # 指数年化标准差
        index_sharpe_ratio,               # 指数夏普
        start_sharpe_ratio,               # 模型夏普
        *export_tail_values(group.stock_code, group.result_id, by_stock),
    ]


def _stock_code_priority(code: str) -> int:
    """stock_code 以 '0' 结尾的优先级为 0（排在最前），其它为 1。"""
    return 0 if code and code.endswith("0") else 1


def _return_beats_value(result: dict[str, Any]) -> float:
    """从 result dict 计算 return_beats = (I16 - I19) * 100，无效时返回负无穷。"""
    val = _safe_subtract(
        _c3_cell_value(result, C3_METRIC_CELLS["annualized_rate"], "annualized_rate"),
        _c3_cell_value(result, C3_METRIC_CELLS["index_annualized_rate"], "index_annualized_rate"),
    )
    value = _safe_float(val)
    return value * 100 if value != float("-inf") else value


def sort_c3_records(records: list[C3ExportRecord]) -> list[C3ExportRecord]:
    """C3 记录多级排序。

    排序优先级（均为降序，除了 stock_code 优先级升序）：
      1. task_name desc（跨任务合并时按任务名分组）
      2. stock_code 以 '0' 结尾优先（升序，priority 0 < 1）
      3. stock_code desc
      4. kline_range 结束时间 desc
      5. return_beats desc（annualized_rate - index_annualized_rate）

    优化：预先计算每条记录的排序键，避免 cmp_to_key 中重复调用耗时的
    _return_beats_value / _stock_code_priority / parse_range_end。
    """

    # 一次性计算所有排序键，存入 dict 避免重复计算
    sort_keys: dict[int, tuple] = {}
    for rec in records:
        sort_keys[id(rec)] = (
            rec.group.task_name,
            _stock_code_priority(rec.group.stock_code),
            rec.group.stock_code,
            parse_range_end(rec.group.kline_range),
            _return_beats_value(rec.group.result),
        )

    def compare(left: C3ExportRecord, right: C3ExportRecord) -> int:
        lk = sort_keys[id(left)]
        rk = sort_keys[id(right)]
        comparisons = [
            compare_desc(lk[0], rk[0]),   # task_name desc
            compare_asc(lk[1], rk[1]),    # stock_code priority asc (0 < 1 → 优先)
            compare_desc(lk[2], rk[2]),   # stock_code desc
            compare_desc(lk[3], rk[3]),   # kline_range end desc
            compare_desc(lk[4], rk[4]),   # return_beats desc
        ]
        return next((v for v in comparisons if v), 0)

    return sorted(records, key=cmp_to_key(compare))


def c3_display_header(columns: list[str]) -> list[str]:
    """将内部列名转换为导出表头显示名称。"""
    return [C3_HEADER_DISPLAY.get(col, col) for col in columns]


def build_c3_worksheets(results: list[dict[str, Any]], by_stock: bool = False) -> list[WorksheetData]:
    records = build_c3_records(results, by_stock)
    display_header = c3_display_header(C3_EXPORT_COLUMNS + export_tail_columns(by_stock))
    if not records:
        return [WorksheetData(name="无K线区间", header=display_header, rows=[])]

    grouped = OrderedDict()
    for record in records:
        key = str(record.group.kline_range or "无K线区间")
        grouped.setdefault(key, []).append(record.row)

    return [
        WorksheetData(name=group_name, header=display_header, rows=rows)
        for group_name, rows in grouped.items()
    ]


def _task_name(task: Any) -> str:
    return str(getattr(task, "name", None) or getattr(task, "id", None) or "task_export")
