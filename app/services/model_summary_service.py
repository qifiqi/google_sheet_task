"""单模型历史结果汇总索引服务。"""

from __future__ import annotations

import json
import math
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Load

from app.extensions import db
from app.models import Task, TaskLog, TaskResult, TaskResultSummaryIndex
from app.services.xpl_service import xpl_analyzer
from app.utils.logger import get_logger
from app.utils.task_authorization import filter_task_types_by_action, normalize_task_type


logger = get_logger(__name__)

SUPPORTED_TASK_TYPES = ("google_sheet", "google_sheet_C4", "google_sheet_C5", "backtest_training")
MODEL_SUMMARY_REBUILD_TASK_TYPE = "model_summary_rebuild"
FINISHED_TASK_STATUSES = ("completed", "cancelled", "error")
SCIENTIFIC_NOTATION_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+$")

SUMMARY_COLUMNS = [
    {"key": "return_rate", "label": "Return%", "format": "percent"},
    {"key": "annualized_rate", "label": "Annualized", "format": "percent"},
    {"key": "max_drawdown", "label": "Max DD%", "format": "percent"},
    {"key": "index_return", "label": "Index Return", "format": "percent"},
    {"key": "index_annualized_rate", "label": "Annualized", "format": "percent"},
    {"key": "index_max_drawdown", "label": "Index max dd", "format": "percent"},
]

RETURN_ANALYSIS_COLUMNS = [
    {"key": "start_monthly_std_dev", "label": "模型月标准差", "format": "number"},
    {"key": "index_monthly_std_dev", "label": "指数月标准差", "format": "number"},
    {"key": "start_annualized_return", "label": "模型年化收益", "format": "percent"},
    {"key": "index_annualized_return", "label": "指数年化收益", "format": "percent"},
    {"key": "start_profit_annual", "label": "模型盈利年份百分比", "format": "percent"},
    {"key": "index_profit_annual", "label": "指数盈利年份百分比", "format": "percent"},
    {"key": "start_profit_monthly_percentage", "label": "模型月盈利百分比", "format": "percent"},
    {"key": "index_profit_monthly_percentage", "label": "指数月盈利百分比", "format": "percent"},
    {"key": "start_avg_monthly_return_common", "label": "模型平均月收益率", "format": "percent"},
    {"key": "index_avg_monthly_return_common", "label": "指数平均月收益率", "format": "percent"},
    {"key": "start_monthly_return_volatility", "label": "模型月收益率波动率", "format": "number"},
    {"key": "index_monthly_return_volatility", "label": "指数月收益率波动率", "format": "number"},
    {"key": "annualized_return_diff", "label": "年化超额收益", "format": "percent"},
    {"key": "outperform_year", "label": "跑赢年份占比", "format": "percent"},
    {"key": "monthly_excess_return_percentage", "label": "月超额胜率", "format": "percent"},
    {"key": "avg_monthly_excess_returns", "label": "平均月超额", "format": "percent"},
    {"key": "monthly_excess_volatility", "label": "月超额波动率", "format": "number"},
    {"key": "max_drawdown_analysis", "label": "年最大超额回撤", "format": "percent"},
    {"key": "excess_drawdown_winning_rate", "label": "超额回撤胜率", "format": "percent"},
    {"key": "start_drawdown", "label": "年最大回撤", "format": "percent"},
    {"key": "start_maximum_number_of_backtest_repair_days", "label": "最大修复天数", "format": "integer"},
    {"key": "excess_maximum_number_of_backtest_repair_days", "label": "超额最大修复天数", "format": "integer"},
    {"key": "start_sharpe_ratio", "label": "模型夏普", "format": "number"},
    {"key": "index_sharpe_ratio", "label": "指数夏普", "format": "number"},
    {"key": "start_kama_ratio", "label": "模型卡玛比率", "format": "number"},
    {"key": "index_kama_ratio", "label": "指数卡玛比率", "format": "number"},
    {"key": "start_sotino_ratio", "label": "模型所提诺比率", "format": "number"},
    {"key": "index_sotino_ratio", "label": "指数所提诺比率", "format": "number"},
    {"key": "excess_sharp", "label": "超额夏普", "format": "number"},
    {"key": "excess_of_promissory_note", "label": "超额所提诺比率", "format": "number"},
]

SUMMARY_COLUMNS = [*SUMMARY_COLUMNS, *RETURN_ANALYSIS_COLUMNS]

BACKTEST_SUMMARY_METRICS = [
    ("absolute_annualized_return", "年化收益"),
    ("absolute_profit_year_percentage", "盈利年份百分比"),
    ("absolute_profit_month_percentage", "月盈利百分比"),
    ("absolute_avg_monthly_return", "平均月收益率"),
    ("absolute_monthly_return_volatility", "月收益率波动率"),
    ("relative_annualized_excess_return", "年化超额收益"),
    ("relative_outperform_year_percentage", "跑赢年份(百分比)"),
    ("relative_monthly_excess_win_rate", "月超额收益胜率"),
    ("relative_avg_monthly_excess", "平均月超额"),
    ("relative_monthly_excess_volatility", "月超额波动率"),
    ("drawdown_annual_max_excess_drawdown", "年最大超额回撤"),
    ("drawdown_excess_drawdown_win_rate", "超额回撤胜率"),
    ("drawdown_annual_max_drawdown", "年最大回撤"),
    ("drawdown_max_repair_days", "最大修复天数"),
    ("drawdown_excess_max_repair_days", "超额最大修复天数"),
    ("ratio_sharpe_ratio", "夏普比率"),
    ("ratio_kama_ratio", "卡玛比率"),
    ("ratio_sortino_ratio", "所提诺比率"),
    ("sharpe_excess_sharpe", "超额夏普"),
    ("sortino_excess_sortino_ratio", "超额所提诺比率"),
]

BACKTEST_SUMMARY_COLUMNS = [
    {"key": key, "label": label}
    for key, label in BACKTEST_SUMMARY_METRICS
]
BACKTEST_SUMMARY_KEY_BY_LABEL = {
    label: key
    for key, label in BACKTEST_SUMMARY_METRICS
}

C3_METRIC_CELLS = {
    "return_rate": "I15",
    "annualized_rate": "I16",
    "max_drawdown": "I17",
    "index_return": "I18",
    "index_annualized_rate": "I19",
    "index_max_drawdown": "I20",
    "fee_total": "I21",
    "fee_annualized": "I22",
    "turnover_rate": "I23",
}

C4_C5_METRIC_CELLS = {
    "return_rate": "D2",
    "annualized_rate": "D3",
    "max_drawdown": "D4",
    "index_return": "D5",
    "index_annualized_rate": "D6",
    "index_max_drawdown": "D7",
    "fee_total": "D8",
    "fee_annualized": "D9",
    "turnover_rate": "D10",
    "return_beats": "D11",
    "dd_beats": "D12",
    "max_one_year_beats": "D13",
    "min_one_year_beats": "D14",
    "max_theoretical_leverage": "D15",
    "avg_theoretical_leverage": "D16",
    "unit_theoretical_leverage_return": "D17",
    "max_actual_leverage": "D18",
    "avg_actual_leverage": "D19",
    "unit_actual_leverage_return": "D20",
}


@dataclass(frozen=True)
class SummaryRecord:
    task_id: str
    task_result_id: int
    task_type: str
    task_name: str
    stock_code: str
    model_key: str
    model_name: str
    year_label: str
    kline_range: str
    parameter_summary: dict[str, Any]
    best_metric_name: str
    best_metric_value: float | None
    metrics: dict[str, Any]
    result_timestamp: datetime | None


def _parse_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _safe_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text == "-":
        return None
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100
        return float(text)
    except (TypeError, ValueError):
        return None


def _fmt_percent_like(value: Any) -> float | None:
    return _safe_number(value)


def _normalize_scientific_text(text: str) -> str:
    if not SCIENTIFIC_NOTATION_RE.fullmatch(text):
        return text
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite():
        return text
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", "+0"} else normalized


def _summary_key_from_label(label: str) -> str:
    text = str(label or "").strip()
    if text in BACKTEST_SUMMARY_KEY_BY_LABEL:
        return BACKTEST_SUMMARY_KEY_BY_LABEL[text]
    slug = re.sub(r"\W+", "_", text.lower(), flags=re.UNICODE).strip("_")
    return f"backtest_{slug}" if slug else ""


def _first_dict_value(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return {}
    value = next(iter(payload.values()))
    return value if isinstance(value, dict) else {}


def _all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def _kline_range(parameters: Any) -> str:
    params = parameters if isinstance(parameters, dict) else {}
    kline = params.get("kline")
    if not isinstance(kline, list):
        return ""
    dated = [
        item for item in kline
        if isinstance(item, dict) and item.get("stock_date")
    ]
    if not dated:
        return ""
    dated.sort(key=lambda item: str(item.get("stock_date") or ""))
    return f"{dated[0].get('stock_date')} ~ {dated[-1].get('stock_date')}"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _parameter_summary(parameters: Any) -> dict[str, Any]:
    if isinstance(parameters, dict):
        summary = {
            "stock_code": parameters.get("stock_code"),
            "task_name": parameters.get("task_name") or parameters.get("name"),
            "year": parameters.get("year") or parameters.get("Kline_key"),
            "A1": parameters.get("A1"),
            "B1": parameters.get("B1"),
        }
        param = parameters.get("parameter")
        if param is not None:
            summary["parameter"] = param
        return {key: value for key, value in summary.items() if value not in (None, "", [])}
    if isinstance(parameters, list):
        return {"parameter": parameters[:-1] if parameters and isinstance(parameters[-1], list) else parameters}
    return {"parameter": parameters}


def _first_text_value(payload: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _display_model_name(raw_name: Any, task_type: str | None = None) -> str:
    text = str(raw_name or "").strip()
    lower_text = text.lower()
    normalized = normalize_task_type(task_type)
    if "c5" in lower_text or normalized == "google_sheet_c5":
        return "C5"
    if "c4" in lower_text or normalized == "google_sheet_c4":
        return "C4"
    return text


def _stock_code_from_task_name(task_type: str | None, task_name: str | None) -> str:
    text = str(task_name or "").strip()
    if not text:
        return ""

    parts = [part.strip() for part in text.split("-") if part.strip()]
    if not parts:
        return ""

    first = parts[0].upper()
    normalized = normalize_task_type(task_type)
    if first in {"C3", "C4", "C5"} and len(parts) >= 2:
        return parts[1].upper()
    if normalized in {"google_sheet", "google_sheet_c4", "google_sheet_c5"}:
        if len(parts) == 1 and any(char.isspace() for char in parts[0]):
            return ""
        return parts[0].upper()
    return parts[0].upper()


def _extract_stock_code(task: Task, parameters: Any) -> str:
    parameter_task_name = _first_text_value(
        parameters,
        ("task_name", "name", "base_task_name", "taskName"),
    )
    parsed = _stock_code_from_task_name(task.task_type, parameter_task_name)
    if parsed:
        return parsed

    config = _parse_json(task.config, {})
    if isinstance(parameters, dict):
        config_from_parameters = parameters.get("config")
        if isinstance(config_from_parameters, dict):
            config = {**config, **config_from_parameters} if isinstance(config, dict) else config_from_parameters

    if isinstance(config, dict):
        parsed = _stock_code_from_task_name(
            task.task_type,
            _first_text_value(config, ("task_name", "name", "base_task_name", "taskName")),
        )
        if parsed:
            return parsed

    parsed = _stock_code_from_task_name(task.task_type, task.name)
    if parsed:
        return parsed

    direct = _first_text_value(parameters, ("stock_code", "stock_no", "code", "symbol"))
    if direct:
        return direct.upper()
    if isinstance(config, dict):
        direct = _first_text_value(config, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return direct.upper()
    return str(task.id).strip().upper()


def _extract_candidate_records(task: Task, result: TaskResult) -> list[SummaryRecord]:
    return [
        row
        for row in extract_summary_records(task, result)
        if row.best_metric_value is not None
    ]


def _extract_return_analysis_metrics(payload: dict[str, Any]) -> dict[str, float]:
    flat_result = payload.get("flat_result")
    if isinstance(flat_result, dict):
        payload = {**payload, **flat_result}

    field_map = {
        "start_monthly_std_dev": "start_monthly_std_dev",
        "index_monthly_std_dev": "index_monthly_std_dev",
        "start_annualized_return": "start_annualized_return",
        "index_annualized_return": "index_annualized_return",
        "start_profit_annual": "start_profit_annual",
        "index_profit_annual": "index_profit_annual",
        "start_profit_monthly_percentage": "start_profit_monthly_percentage",
        "index_profit_monthly_percentage": "index_profit_monthly_percentage",
        "start_avg_monthly_return_common": "start_avg_monthly_return_common",
        "index_avg_monthly_return_common": "index_avg_monthly_return_common",
        "start_monthly_return_volatility": "start_monthly_return_volatility",
        "index_monthly_return_volatility": "index_monthly_return_volatility",
        "annualized_return_diff": "annualized_return_diff",
        "outperform_year": "outperform_year",
        "monthly_excess_return_percentage": "monthly_excess_return_percentage_last_return",
        "avg_monthly_excess_returns": "avg_monthly_excess_returns",
        "monthly_excess_volatility": "monthly_excess_volatility",
        "max_drawdown_analysis": "max_drawdown",
        "excess_drawdown_winning_rate": "excess_drawdown_winning_rate",
        "start_drawdown": "start_drawdown",
        "start_maximum_number_of_backtest_repair_days": "start_maximum_number_of_backtest_repair_days",
        "excess_maximum_number_of_backtest_repair_days": "excess_maximum_number_of_backtest_repair_days",
        "start_sharpe_ratio": "start_sharpe_ratio",
        "index_sharpe_ratio": "index_sharpe_ratio",
        "start_kama_ratio": "start_kama_ratio",
        "index_kama_ratio": "index_kama_ratio",
        "start_sotino_ratio": "start_sotino_ratio",
        "index_sotino_ratio": "index_sotino_ratio",
        "excess_sharp": "excess_sharp",
        "excess_of_promissory_note": "excess_of_promissory_note",
    }
    metrics = {}
    for output_key, source_key in field_map.items():
        value = _safe_number(payload.get(source_key))
        if value is not None:
            metrics[output_key] = value
    return metrics


def _first_safe_number(*values: Any) -> float | None:
    for value in values:
        number = _safe_number(value)
        if number is not None:
            return number
    return None


def _extract_c3(task: Task, result: TaskResult) -> list[SummaryRecord]:
    parameters = _parse_json(result.parameters, [])
    payload = _parse_json(result.result, {})
    if not isinstance(payload, dict):
        return []

    return_rate = _fmt_percent_like(payload.get("I15"))
    metrics = {key: _fmt_percent_like(payload.get(cell)) for key, cell in C3_METRIC_CELLS.items()}
    index_return = metrics.get("index_return")
    return_beats = round(return_rate - index_return, 12) if return_rate is not None and index_return is not None else None
    metrics["return_beats"] = return_beats
    metrics.update(_extract_return_analysis_metrics(payload))
    summary = _parameter_summary(parameters)
    return [
        SummaryRecord(
            task_id=task.id,
            task_result_id=result.id,
            task_type=task.task_type,
            task_name=task.name,
            stock_code=_extract_stock_code(task, parameters),
            model_key="default",
            model_name="C3",
            year_label=str(summary.get("year") or ""),
            kline_range=_kline_range({"kline": parameters[-1]} if isinstance(parameters, list) and parameters else parameters),
            parameter_summary=summary,
            best_metric_name="ReturnBeats",
            best_metric_value=return_beats,
            metrics={key: value for key, value in metrics.items() if value is not None},
            result_timestamp=result.timestamp,
        )
    ]


def _extract_c4_c5(task: Task, result: TaskResult) -> list[SummaryRecord]:
    parameters = _parse_json(result.parameters, {})
    payload = _parse_json(result.result, {})
    if not isinstance(payload, dict):
        return []

    records = []
    for model_key, raw_metrics in payload.items():
        if model_key == "flat_result" or not isinstance(raw_metrics, dict):
            continue

        return_beats = _safe_number(raw_metrics.get("D11"))
        if return_beats is None:
            left = _safe_number(raw_metrics.get("D2"))
            right = _safe_number(raw_metrics.get("D5"))
            return_beats = left - right if left is not None and right is not None else None
        start_xpl = raw_metrics.get("start_return_xpl") if isinstance(raw_metrics.get("start_return_xpl"), dict) else {}
        index_xpl = raw_metrics.get("index_return_xpl") if isinstance(raw_metrics.get("index_return_xpl"), dict) else {}
        key_parts = str(model_key).split("__")
        model_name = "__".join(key_parts[1:]) if len(key_parts) > 1 else str(model_key)
        model_name = _display_model_name(model_name, task.task_type)
        metrics = {
            key: _safe_number(raw_metrics.get(cell))
            for key, cell in C4_C5_METRIC_CELLS.items()
        }
        metrics.update({"return_beats": return_beats})
        metrics.update(_extract_return_analysis_metrics(raw_metrics))
        metrics.update({
            "start_sharpe_ratio": _first_safe_number(
                start_xpl.get("sharpe_ratio"),
                metrics.get("start_sharpe_ratio"),
            ),
            "index_sharpe_ratio": _first_safe_number(
                index_xpl.get("sharpe_ratio"),
                metrics.get("index_sharpe_ratio"),
            ),
        })
        records.append(
            SummaryRecord(
                task_id=task.id,
                task_result_id=result.id,
                task_type=task.task_type,
                task_name=task.name,
                stock_code=_extract_stock_code(task, parameters),
                model_key=str(model_key),
                model_name=model_name,
                year_label=str(parameters.get("year") or parameters.get("Kline_key") or ""),
                kline_range=_kline_range(parameters),
                parameter_summary=_parameter_summary(parameters),
                best_metric_name="ReturnBeats",
                best_metric_value=return_beats,
                metrics={key: value for key, value in metrics.items() if value is not None},
                result_timestamp=result.timestamp,
            )
        )
    return records


def _extract_c5(task: Task, result: TaskResult) -> list[SummaryRecord]:
    return _extract_c4_c5(task, result)


def _format_backtest_percent(value: Any) -> str:
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2%}"


def _format_backtest_number(value: Any) -> str:
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _negative_number(value: Any) -> float | None:
    number = _safe_number(value)
    return -number if number is not None else None


def _normalize_backtest_display_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    while text.startswith("--"):
        text = text[1:]
    return _normalize_scientific_text(text)


def _extract_backtest_metric_values(calculate_metrics: dict[str, Any]) -> dict[str, str]:
    excess_all = _all_entry(calculate_metrics.get("excess_returns"))
    index_profit_monthly_all = _all_entry(calculate_metrics.get("index_profit_monthly"))
    start_profit_monthly_all = _all_entry(calculate_metrics.get("start_profit_monthly"))
    start_kama_all = _all_entry(calculate_metrics.get("start_kama_ratio"))
    start_sotino_all = _all_entry(calculate_metrics.get("start_sotino_ratio"))
    monthly_excess_percentage_all = _all_entry(calculate_metrics.get("monthly_excess_return_percentage"))
    start_sharpe_all = (
        (calculate_metrics.get("start_sharpe_ratios") or {}).get("all")
        if isinstance(calculate_metrics.get("start_sharpe_ratios"), dict)
        else {}
    ) or {}

    monthly_excess_returns = calculate_metrics.get("monthly_excess_returns") or []
    valid_excess_months = [
        item.get("monthly_excess_return_diff")
        for item in monthly_excess_returns
        if isinstance(item, dict) and item.get("monthly_excess_return_diff") is not None
    ]
    avg_monthly_excess_returns = (
        sum(valid_excess_months) / len(valid_excess_months) if valid_excess_months else None
    )

    max_drawdown = None
    try:
        index_max_dd = calculate_metrics.get("index_maximum_drawdown") or {}
        start_max_dd = calculate_metrics.get("start_maximum_drawdown") or {}
        year_excess_returns = [
            int(item["year"])
            for item in (calculate_metrics.get("excess_returns") or [])
            if isinstance(item, dict)
            and item.get("year") != "all"
            and item.get("annualized_return_diff") is not None
            and item.get("annualized_return_diff") > 0
        ]
        index_year_map = {
            item["year"]: item
            for item in index_max_dd.get("year_maximum_drawdown", [])
            if isinstance(item, dict) and item.get("year") in year_excess_returns
        }
        start_year_map = {
            item["year"]: item
            for item in start_max_dd.get("year_maximum_drawdown", [])
            if isinstance(item, dict) and item.get("year") in year_excess_returns
        }
        diffs = [
            (start_year_map.get(year) or {})["drawdown"] - index_item["drawdown"]
            for year, index_item in index_year_map.items()
            if index_item.get("drawdown") is not None
            and (start_year_map.get(year) or {}).get("drawdown") is not None
        ]
        max_drawdown = max(diffs) if diffs else None
    except Exception:
        max_drawdown = None

    total_max_drawdown = ((calculate_metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown") or {})
    return {
        "absolute_annualized_return": _format_backtest_percent(excess_all.get("start_annualized_return")),
        "absolute_profit_year_percentage": _format_backtest_percent(calculate_metrics.get("start_profit_annual")),
        "absolute_profit_month_percentage": _format_backtest_percent(start_profit_monthly_all.get("profit_monthly_percentage")),
        "absolute_avg_monthly_return": _format_backtest_percent(start_sharpe_all.get("avg_monthly_return")),
        "absolute_monthly_return_volatility": _format_backtest_percent(calculate_metrics.get("start_monthly_return_volatility")),
        "relative_annualized_excess_return": _format_backtest_percent(excess_all.get("annualized_return_diff")),
        "relative_outperform_year_percentage": _format_backtest_percent(calculate_metrics.get("outperform_year")),
        "relative_monthly_excess_win_rate": _format_backtest_percent(monthly_excess_percentage_all.get("excess_return")),
        "relative_avg_monthly_excess": _format_backtest_percent(avg_monthly_excess_returns),
        "relative_monthly_excess_volatility": _format_backtest_percent(calculate_metrics.get("monthly_excess_volatility")),
        "drawdown_annual_max_excess_drawdown": _format_backtest_percent(-max_drawdown) if max_drawdown is not None else "",
        "drawdown_excess_drawdown_win_rate": (
            _format_backtest_percent(_negative_number(calculate_metrics.get("excess_drawdown_winning_rate")))
            if calculate_metrics.get("excess_drawdown_winning_rate") is not None
            else ""
        ),
        "drawdown_annual_max_drawdown": (
            _format_backtest_percent(_negative_number(total_max_drawdown.get("drawdown")))
            if total_max_drawdown.get("drawdown") is not None
            else ""
        ),
        "drawdown_max_repair_days": str(calculate_metrics.get("start_maximum_number_of_backtest_repair_days") or ""),
        "drawdown_excess_max_repair_days": str(calculate_metrics.get("excess_maximum_number_of_backtest_repair_days") or ""),
        "ratio_sharpe_ratio": _format_backtest_number(start_sharpe_all.get("sharpe_ratio")),
        "ratio_kama_ratio": _format_backtest_number(start_kama_all.get("kama_ratio")),
        "ratio_sortino_ratio": _format_backtest_number(start_sotino_all.get("sotino_ratio")),
        "sharpe_excess_sharpe": _format_backtest_number(calculate_metrics.get("excess_sharp")),
        "sortino_excess_sortino_ratio": _format_backtest_number(calculate_metrics.get("excess_of_promissory_note")),
    }


def _extract_backtest_summary_rows(calculate_metrics: dict[str, Any], model_name: str) -> tuple[str, list[dict[str, str]]]:
    def _safe_all_entry(items: Any) -> dict[str, Any]:
        return _all_entry(items, "year")

    def _fallback_rows() -> tuple[str, list[dict[str, str]]]:
        excess_all = _safe_all_entry(calculate_metrics.get("excess_returns"))
        index_profit_monthly_all = _safe_all_entry(calculate_metrics.get("index_profit_monthly"))
        start_profit_monthly_all = _safe_all_entry(calculate_metrics.get("start_profit_monthly"))
        index_kama_all = _safe_all_entry(calculate_metrics.get("index_kama_ratio"))
        start_kama_all = _safe_all_entry(calculate_metrics.get("start_kama_ratio"))
        index_sotino_all = _safe_all_entry(calculate_metrics.get("index_sotino_ratio"))
        start_sotino_all = _safe_all_entry(calculate_metrics.get("start_sotino_ratio"))
        monthly_excess_percentage_all = _safe_all_entry(calculate_metrics.get("monthly_excess_return_percentage"))
        start_sharpe_all = (calculate_metrics.get("start_sharpe_ratios") or {}).get("all") or {}

        monthly_excess_returns = calculate_metrics.get("monthly_excess_returns") or []
        valid_excess_months = [
            item.get("monthly_excess_return_diff")
            for item in monthly_excess_returns
            if isinstance(item, dict) and item.get("monthly_excess_return_diff") is not None
        ]
        avg_monthly_excess_returns = (
            sum(valid_excess_months) / len(valid_excess_months) if valid_excess_months else None
        )

        max_drawdown = None
        try:
            index_max_dd = calculate_metrics.get("index_maximum_drawdown") or {}
            start_max_dd = calculate_metrics.get("start_maximum_drawdown") or {}
            year_excess_returns = [
                int(item["year"])
                for item in (calculate_metrics.get("excess_returns") or [])
                if isinstance(item, dict)
                and item.get("year") != "all"
                and item.get("annualized_return_diff") is not None
                and item.get("annualized_return_diff") > 0
            ]
            index_year_map = {
                item["year"]: item
                for item in index_max_dd.get("year_maximum_drawdown", [])
                if isinstance(item, dict) and item.get("year") in year_excess_returns
            }
            start_year_map = {
                item["year"]: item
                for item in start_max_dd.get("year_maximum_drawdown", [])
                if isinstance(item, dict) and item.get("year") in year_excess_returns
            }
            diffs = [
                (start_year_map.get(year) or {})["drawdown"] - index_item["drawdown"]
                for year, index_item in index_year_map.items()
                if index_item.get("drawdown") is not None
                and (start_year_map.get(year) or {}).get("drawdown") is not None
            ]
            max_drawdown = max(diffs) if diffs else None
        except Exception:
            max_drawdown = None

        total_max_drawdown = ((calculate_metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown") or {})
        period_text = str(excess_all.get("start_end_date") or "")
        rows = [
            ("年化收益", _format_backtest_percent(excess_all.get("start_annualized_return"))),
            ("盈利年份百分比", _format_backtest_percent(calculate_metrics.get("start_profit_annual"))),
            ("月盈利百分比", _format_backtest_percent(start_profit_monthly_all.get("profit_monthly_percentage"))),
            ("平均月收益率", _format_backtest_percent(start_sharpe_all.get("avg_monthly_return"))),
            ("月收益率波动率", _format_backtest_percent(calculate_metrics.get("start_monthly_return_volatility"))),
            ("年化超额收益", _format_backtest_percent(excess_all.get("annualized_return_diff"))),
            ("跑赢年份(百分比)", _format_backtest_percent(calculate_metrics.get("outperform_year"))),
            ("月超额收益胜率", _format_backtest_percent(monthly_excess_percentage_all.get("excess_return"))),
            ("平均月超额", _format_backtest_percent(avg_monthly_excess_returns)),
            ("月超额波动率", _format_backtest_percent(calculate_metrics.get("monthly_excess_volatility"))),
            ("年最大超额回撤", _format_backtest_percent(-max_drawdown) if max_drawdown is not None else ""),
            (
                "超额回撤胜率",
                _format_backtest_percent(_negative_number(calculate_metrics.get("excess_drawdown_winning_rate")))
                if calculate_metrics.get("excess_drawdown_winning_rate") is not None
                else "",
            ),
            (
                "年最大回撤",
                _format_backtest_percent(_negative_number(total_max_drawdown.get("drawdown")))
                if total_max_drawdown.get("drawdown") is not None
                else "",
            ),
            ("最大修复天数", str(calculate_metrics.get("start_maximum_number_of_backtest_repair_days") or "")),
            ("超额最大修复天数", str(calculate_metrics.get("excess_maximum_number_of_backtest_repair_days") or "")),
            ("夏普比率", _format_backtest_number(start_sharpe_all.get("sharpe_ratio"))),
            ("卡玛比率", _format_backtest_number(start_kama_all.get("kama_ratio"))),
            ("所提诺比率", _format_backtest_number(start_sotino_all.get("sotino_ratio"))),
            ("超额夏普", _format_backtest_number(calculate_metrics.get("excess_sharp"))),
            ("超额所提诺比率", _format_backtest_number(calculate_metrics.get("excess_of_promissory_note"))),
        ]
        return period_text, [{"metric": metric, "model_value": value} for metric, value in rows]

    try:
        summary_df = xpl_analyzer.format_export_file_data({
            "analyze_result": calculate_metrics,
            "filename_title": model_name,
        })
    except Exception:
        return _fallback_rows()

    period_text = str(summary_df.iat[1, 1] or "").strip()
    rows = []
    for row_index in range(3, 23):
        metric = str(summary_df.iat[row_index, 1] or "").strip()
        if not metric:
            continue
        rows.append({
            "metric": metric,
            "model_value": _normalize_backtest_display_value(summary_df.iat[row_index, 3]),
        })
    return period_text, rows


def _extract_backtest(task: Task, result: TaskResult) -> list[SummaryRecord]:
    parameters = _parse_json(result.parameters, {})
    payload = _parse_json(result.result, {})
    core = _first_dict_value(payload)
    calculate_metrics = core.get("calculate_metrics") if isinstance(core.get("calculate_metrics"), dict) else {}
    if not calculate_metrics:
        return []

    period_text, summary_rows = _extract_backtest_summary_rows(calculate_metrics, task.name)
    metrics = {}
    for summary_row in summary_rows:
        metric_key = _summary_key_from_label(summary_row.get("metric", ""))
        if metric_key:
            metrics[metric_key] = summary_row.get("model_value")
    metrics.update({
        key: value
        for key, value in _extract_backtest_metric_values(calculate_metrics).items()
        if value not in (None, "")
    })
    annualized_diff = _safe_number(metrics.get("relative_annualized_excess_return"))
    if annualized_diff is None:
        annualized_diff = _safe_number((_all_entry(calculate_metrics.get("excess_returns"))).get("annualized_return_diff"))
    return [
        SummaryRecord(
            task_id=task.id,
            task_result_id=result.id,
            task_type=task.task_type,
            task_name=task.name,
            stock_code=_extract_stock_code(task, parameters),
            model_key="default",
            model_name="回测",
            year_label=str(parameters.get("year") or parameters.get("Kline_key") or ""),
            kline_range=period_text or _kline_range(parameters),
            parameter_summary=_parameter_summary(parameters),
            best_metric_name="年化超额收益",
            best_metric_value=annualized_diff,
            metrics={key: value for key, value in metrics.items() if value not in (None, "")},
            result_timestamp=result.timestamp,
        )
    ]


def extract_summary_records(task: Task, result: TaskResult) -> list[SummaryRecord]:
    if not result.success:
        return []
    normalized = normalize_task_type(task.task_type) or str(task.task_type or "")
    if normalized == "google_sheet":
        return _extract_c3(task, result)
    if normalized == "google_sheet_c4":
        return _extract_c4_c5(task, result)
    if normalized == "google_sheet_c5":
        return _extract_c5(task, result)
    if normalized == "backtest_training":
        return _extract_backtest(task, result)
    return []


class ModelSummaryService:
    """维护和查询单模型汇总索引。"""

    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._index_lock = threading.RLock()

    def upsert_task_result(self, task_result_id: int, *, commit: bool = True) -> int:
        with self._index_lock:
            return self._upsert_task_result_locked(task_result_id, commit=commit)

    def upsert_task(self, task_id: str, *, commit: bool = True) -> dict[str, int]:
        """Rebuild summary index rows for one task from all successful results."""
        if not task_id:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}
        with self._index_lock:
            summary = self._upsert_task_batch([task_id])
            if commit:
                db.session.commit()
            return summary

    def _upsert_task_result_locked(self, task_result_id: int, *, commit: bool = True) -> int:
        record = (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .filter(TaskResult.id == task_result_id)
            .first()
        )
        if not record:
            return 0
        task, result = record
        rows = _extract_candidate_records(task, result)
        existing = {
            item.model_key: item
            for item in TaskResultSummaryIndex.query.filter_by(task_result_id=result.id).all()
        }
        changed_task_ids = set()
        for row in rows:
            item = existing.get(row.model_key)
            if item is None:
                item = TaskResultSummaryIndex(task_result_id=row.task_result_id, model_key=row.model_key)
                db.session.add(item)
            self._apply_record(item, row)
            changed_task_ids.add(row.task_id)

        stale_keys = set(existing) - {row.model_key for row in rows}
        for key in stale_keys:
            changed_task_ids.add(existing[key].task_id)
            db.session.delete(existing[key])
        db.session.flush()

        for changed_task_id in changed_task_ids:
            self._keep_only_best_for_task(changed_task_id)
        if commit:
            db.session.commit()
        return len(rows)

    def rebuild(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        progress_task_id: str | None = None,
    ) -> dict[str, int]:
        with self._index_lock:
            return self._rebuild_locked(
                task_type=task_type,
                task_id=task_id,
                batch_size=batch_size,
                reset=reset,
                progress_task_id=progress_task_id,
            )

    def _rebuild_locked(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        progress_task_id: str | None = None,
    ) -> dict[str, int]:
        if reset:
            delete_query = TaskResultSummaryIndex.query
            if task_id:
                delete_query = delete_query.filter(TaskResultSummaryIndex.task_id == task_id)
            if task_type:
                delete_query = delete_query.filter(TaskResultSummaryIndex.task_type == task_type)
            deleted = delete_query.delete(synchronize_session=False)
            db.session.commit()
        else:
            deleted = 0

        processed = 0
        processed_tasks = 0
        candidate_records = 0
        batch_size = max(1, min(int(batch_size or 20), 20))
        task_ids = self._load_rebuild_task_ids(task_type=task_type, task_id=task_id)
        total = len(task_ids)
        if progress_task_id:
            self._update_rebuild_task(
                progress_task_id,
                total_steps=total,
                current_step=0,
                message=f"准备重建索引，预计扫描 {total} 个任务，每批 {batch_size} 个任务",
            )

        for start in range(0, len(task_ids), batch_size):
            batch_task_ids = task_ids[start:start + batch_size]
            batch_result = self._upsert_task_batch(batch_task_ids)
            processed += batch_result["processed"]
            processed_tasks += batch_result["processed_tasks"]
            candidate_records += batch_result["candidate_records"]
            if progress_task_id:
                self._update_rebuild_task(
                    progress_task_id,
                    current_step=processed_tasks,
                    message=(
                        f"已处理 {processed_tasks}/{total} 个任务，"
                        f"扫描 {processed} 条结果，解析候选 {candidate_records} 条"
                    ),
                )
            db.session.commit()

        deduped = self._dedupe_best_per_task(task_type=task_type, task_id=task_id)
        indexed = self._count_index_rows(task_type=task_type, task_id=task_id)
        if progress_task_id:
            self._update_rebuild_task(
                progress_task_id,
                current_step=processed_tasks,
                total_steps=total,
                message=f"索引表当前保留 {indexed} 条任务最优记录，去重删除 {deduped} 条",
            )
        return {
            "processed": processed,
            "processed_tasks": processed_tasks,
            "indexed": indexed,
            "candidate_records": candidate_records,
            "deleted": deleted,
            "deduped": deduped,
        }

    def start_rebuild_job(
        self,
        app,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        created_by_user_id: int | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        rebuild_task = Task(
            id=job_id,
            name="单模型汇总索引重建",
            description="后台扫描历史 task_results，重建任务/股票汇总查询索引",
            task_type=MODEL_SUMMARY_REBUILD_TASK_TYPE,
            status="pending",
            config=json.dumps(
                {
                    "task_type": task_type,
                    "task_id": task_id,
                    "batch_size": batch_size,
                    "reset": reset,
                },
                ensure_ascii=False,
            ),
            total_steps=0,
            current_step=0,
            created_by_user_id=created_by_user_id,
        )
        db.session.add(rebuild_task)
        db.session.add(TaskLog(task_id=job_id, level="info", message="索引重建任务已创建"))
        db.session.commit()

        job = {
            "job_id": job_id,
            "task_id": job_id,
            "status": "pending",
            "message": "索引重建任务已创建",
            "params": {
                "task_type": task_type,
                "task_id": task_id,
                "batch_size": batch_size,
                "reset": reset,
            },
            "result": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
        }
        with self._jobs_lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_rebuild_job,
            args=(app, job_id),
            daemon=True,
            name=f"model-summary-rebuild-{job_id[:8]}",
        )
        thread.start()
        return job.copy()

    def get_rebuild_job(self, job_id: str) -> dict[str, Any] | None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                return self._job_with_task_status(dict(job))
        return self._job_from_task(job_id)

    def latest_rebuild_job(self) -> dict[str, Any] | None:
        with self._jobs_lock:
            if not self._jobs:
                task = (
                    Task.query
                    .filter_by(task_type=MODEL_SUMMARY_REBUILD_TASK_TYPE)
                    .order_by(Task.created_at.desc())
                    .first()
                )
                return self._job_from_task(task.id) if task else None
            job = max(self._jobs.values(), key=lambda item: item.get("started_at") or "")
            return self._job_with_task_status(dict(job))

    def _run_rebuild_job(self, app, job_id: str) -> None:
        with self._jobs_lock:
            job = self._jobs[job_id]
            params = dict(job["params"])
        try:
            with app.app_context():
                self._update_rebuild_task(
                    job_id,
                    status="running",
                    start_time=datetime.now(),
                    message="索引重建开始执行",
                )
                with self._jobs_lock:
                    self._jobs[job_id].update({
                        "status": "running",
                        "message": "索引重建开始执行",
                    })
                result = self.rebuild(**params, progress_task_id=job_id)
                with self._jobs_lock:
                    self._jobs[job_id].update({
                        "result": result,
                    })
                self._update_rebuild_task(
                    job_id,
                    status="completed",
                    end_time=datetime.now(),
                    current_step=result.get("processed_tasks", 0),
                    message=(
                        f"索引重建完成：处理 {result.get('processed_tasks', 0)} 个任务、"
                        f"{result.get('processed', 0)} 条结果，"
                        f"保留 {result.get('indexed', 0)} 条任务最优索引，"
                        f"删除 {result.get('deleted', 0)} 条旧索引，"
                        f"去重 {result.get('deduped', 0)} 条"
                    ),
                )
            with self._jobs_lock:
                self._jobs[job_id].update({
                    "status": "completed",
                    "message": "索引重建完成",
                    "finished_at": datetime.now().isoformat(),
                })
        except Exception as exc:
            logger.error("后台重建单模型汇总索引失败: %s", exc, exc_info=True)
            with app.app_context():
                self._update_rebuild_task(
                    job_id,
                    status="error",
                    end_time=datetime.now(),
                    error_message=str(exc),
                    message=f"索引重建失败: {exc}",
                    level="error",
                )
            with self._jobs_lock:
                self._jobs[job_id].update({
                    "status": "error",
                    "message": "索引重建失败",
                    "error": str(exc),
                    "finished_at": datetime.now().isoformat(),
                })

    def query(self, user: Any, filters: dict[str, Any]) -> dict[str, Any]:
        page = max(int(filters.get("page") or 1), 1)
        per_page = min(max(int(filters.get("per_page") or 50), 1), 200)
        task_type = str(filters.get("task_type") or "").strip()
        stock_code = str(filters.get("stock_code") or "").strip()
        best_only = str(filters.get("best_only", "true")).lower() not in {"false", "0", "no"}
        if not best_only:
            return self._query_all_results(user, filters, page, per_page, task_type, stock_code)

        query = TaskResultSummaryIndex.query

        allowed_types = filter_task_types_by_action(user, "view", SUPPORTED_TASK_TYPES)
        if not allowed_types:
            return self._empty_response(page, per_page)

        if task_type:
            if task_type not in allowed_types:
                return self._empty_response(page, per_page, columns=self._columns_for_task_type(task_type))
            query = query.filter(TaskResultSummaryIndex.task_type == task_type)
        else:
            visible_types = [
                allowed_type
                for allowed_type in allowed_types
                if normalize_task_type(allowed_type) != "backtest_training"
            ]
            if not visible_types:
                return self._empty_response(page, per_page)
            query = query.filter(TaskResultSummaryIndex.task_type.in_(visible_types))
        if stock_code:
            query = query.filter(TaskResultSummaryIndex.stock_code.ilike(f"%{stock_code}%"))
        task_id = str(filters.get("task_id") or "").strip()
        if task_id:
            query = query.filter(TaskResultSummaryIndex.task_id == task_id)
        result_id = filters.get("result_id")
        if result_id:
            query = query.filter(TaskResultSummaryIndex.task_result_id == int(result_id))
        summary_type = str(filters.get("summary_type") or "task").strip().lower()
        if summary_type not in {"task", "stock"}:
            summary_type = "task"
        if summary_type == "stock":
            query = query.filter(TaskResultSummaryIndex.is_best == True)

        if summary_type == "stock":
            query = query.filter(
                TaskResultSummaryIndex.stock_code.isnot(None),
                TaskResultSummaryIndex.stock_code != "",
            )
            query = self._stock_summary_query(query)
        else:
            query = query.order_by(
                TaskResultSummaryIndex.task_type.asc(),
                TaskResultSummaryIndex.stock_code.asc(),
                TaskResultSummaryIndex.best_metric_value.desc(),
                TaskResultSummaryIndex.result_timestamp.desc(),
                TaskResultSummaryIndex.id.desc(),
            )
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            "status": "success",
            "summary_type": summary_type,
            "columns": self._columns_for_task_type(task_type),
            "items": [item.to_dict() for item in pagination.items],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_prev": pagination.has_prev,
                "has_next": pagination.has_next,
            },
        }

    def _apply_record(self, item: TaskResultSummaryIndex, row: SummaryRecord) -> None:
        item.task_id = row.task_id
        item.task_result_id = row.task_result_id
        item.task_type = row.task_type
        item.task_name = row.task_name
        item.stock_code = row.stock_code
        item.model_key = row.model_key
        item.model_name = row.model_name
        item.year_label = row.year_label
        item.kline_range = row.kline_range
        item.parameter_summary = _json_text(row.parameter_summary)
        item.best_metric_name = row.best_metric_name
        item.best_metric_value = row.best_metric_value
        item.metrics_json = _json_text(row.metrics)
        item.result_timestamp = row.result_timestamp

    def _record_to_dict(self, row: SummaryRecord) -> dict[str, Any]:
        return {
            "id": None,
            "task_id": row.task_id,
            "task_result_id": row.task_result_id,
            "task_type": row.task_type,
            "task_name": row.task_name,
            "stock_code": row.stock_code,
            "model_key": row.model_key,
            "model_name": row.model_name,
            "year_label": row.year_label,
            "kline_range": row.kline_range,
            "parameter_summary": row.parameter_summary,
            "best_metric_name": row.best_metric_name,
            "best_metric_value": row.best_metric_value,
            "metrics": row.metrics,
            "is_best": False,
            "result_timestamp": row.result_timestamp.isoformat() if row.result_timestamp else None,
            "created_at": None,
            "updated_at": None,
        }

    def _query_all_results(
        self,
        user: Any,
        filters: dict[str, Any],
        page: int,
        per_page: int,
        task_type: str,
        stock_code: str,
    ) -> dict[str, Any]:
        columns = self._columns_for_task_type(task_type)
        if not stock_code:
            return {
                "status": "error",
                "message": "查询全部结果时必须输入单个股票代码",
            }

        allowed_types = filter_task_types_by_action(user, "view", SUPPORTED_TASK_TYPES)
        if not allowed_types:
            return self._empty_response(page, per_page, columns=columns)
        if task_type:
            if task_type not in allowed_types:
                return self._empty_response(page, per_page, columns=columns)
            visible_types = [task_type]
        else:
            visible_types = [
                allowed_type
                for allowed_type in allowed_types
                if normalize_task_type(allowed_type) != "backtest_training"
            ]
        if not visible_types:
            return self._empty_response(page, per_page, columns=columns)

        task_id = str(filters.get("task_id") or "").strip()
        result_id = filters.get("result_id")
        query = (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .options(
                Load(Task).load_only(Task.id, Task.name, Task.task_type, Task.config),
                Load(TaskResult).load_only(
                    TaskResult.id,
                    TaskResult.task_id,
                    TaskResult.parameters,
                    TaskResult.result,
                    TaskResult.success,
                    TaskResult.timestamp,
                ),
            )
            .filter(Task.task_type.in_(visible_types), TaskResult.success == True)
        )
        if task_id:
            query = query.filter(Task.id == task_id)
        if result_id:
            query = query.filter(TaskResult.id == int(result_id))

        rows: list[SummaryRecord] = []
        normalized_stock_code = stock_code.upper()
        for task, result in query.order_by(TaskResult.timestamp.desc(), TaskResult.id.desc()).all():
            for row in _extract_candidate_records(task, result):
                if row.stock_code.upper() == normalized_stock_code:
                    rows.append(row)

        total = len(rows)
        start = (page - 1) * per_page
        paged_rows = rows[start:start + per_page]
        pages = math.ceil(total / per_page) if total else 0
        return {
            "status": "success",
            "summary_type": str(filters.get("summary_type") or "task"),
            "columns": columns,
            "items": [self._record_to_dict(row) for row in paged_rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
                "has_prev": page > 1,
                "has_next": page < pages,
            },
        }

    def _upsert_batch(self, batch: list[tuple[Task, TaskResult]]) -> int:
        result_ids = [result.id for _task, result in batch]
        existing_items = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.task_result_id.in_(result_ids))
            .all()
            if result_ids
            else []
        )
        existing = {
            (item.task_result_id, item.model_key): item
            for item in existing_items
        }
        seen_keys = set()
        changed_task_ids = set()
        indexed = 0

        for task, result in batch:
            rows = _extract_candidate_records(task, result)
            indexed += len(rows)
            for row in rows:
                key = (row.task_result_id, row.model_key)
                seen_keys.add(key)
                item = existing.get(key)
                if item is None:
                    item = TaskResultSummaryIndex(
                        task_result_id=row.task_result_id,
                        model_key=row.model_key,
                    )
                    db.session.add(item)
                self._apply_record(item, row)
                changed_task_ids.add(row.task_id)

        for key, item in existing.items():
            if key not in seen_keys:
                changed_task_ids.add(item.task_id)
                db.session.delete(item)

        db.session.flush()
        for changed_task_id in changed_task_ids:
            self._keep_only_best_for_task(changed_task_id)
        return indexed

    def _load_rebuild_task_ids(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
    ) -> list[str]:
        query = db.session.query(Task.id).filter(Task.status.in_(FINISHED_TASK_STATUSES))
        if task_type:
            query = query.filter(Task.task_type == task_type)
        else:
            query = query.filter(Task.task_type.in_(SUPPORTED_TASK_TYPES))
        if task_id:
            query = query.filter(Task.id == task_id)
        rows = (
            query
            .order_by(Task.created_at.asc(), Task.id.asc())
            .all()
        )
        return [row[0] for row in rows]

    def _upsert_task_batch(self, task_ids: list[str]) -> dict[str, int]:
        if not task_ids:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}

        batch = (
            db.session.query(Task, TaskResult)
            .join(TaskResult, TaskResult.task_id == Task.id)
            .options(
                Load(Task).load_only(Task.id, Task.name, Task.task_type, Task.config),
                Load(TaskResult).load_only(
                    TaskResult.id,
                    TaskResult.task_id,
                    TaskResult.parameters,
                    TaskResult.result,
                    TaskResult.success,
                    TaskResult.timestamp,
                ),
            )
            .filter(Task.id.in_(task_ids), TaskResult.success == True)
            .order_by(Task.id.asc(), TaskResult.id.asc())
            .all()
        )
        best_by_task: dict[str, SummaryRecord] = {}
        candidate_records = 0

        for task, result in batch:
            for row in _extract_candidate_records(task, result):
                candidate_records += 1
                current = best_by_task.get(row.task_id)
                if current is None or self._is_better_record(row, current):
                    best_by_task[row.task_id] = row

        TaskResultSummaryIndex.query.filter(
            TaskResultSummaryIndex.task_id.in_(task_ids)
        ).delete(synchronize_session=False)
        db.session.flush()

        for row in best_by_task.values():
            item = TaskResultSummaryIndex(
                task_result_id=row.task_result_id,
                model_key=row.model_key,
                is_best=True,
            )
            self._apply_record(item, row)
            db.session.add(item)

        db.session.flush()
        return {
            "processed": len(batch),
            "processed_tasks": len(task_ids),
            "candidate_records": candidate_records,
        }

    def _is_better_record(self, candidate: SummaryRecord, current: SummaryRecord) -> bool:
        candidate_value = candidate.best_metric_value
        current_value = current.best_metric_value
        if candidate_value is None:
            return False
        if current_value is None:
            return True
        if candidate_value != current_value:
            return candidate_value > current_value
        candidate_timestamp = candidate.result_timestamp or datetime.min
        current_timestamp = current.result_timestamp or datetime.min
        if candidate_timestamp != current_timestamp:
            return candidate_timestamp > current_timestamp
        return candidate.task_result_id > current.task_result_id

    def _stock_summary_query(self, query):
        subquery = (
            query
            .with_entities(
                TaskResultSummaryIndex.id.label("id"),
                func.row_number().over(
                    partition_by=TaskResultSummaryIndex.stock_code,
                    order_by=(
                        TaskResultSummaryIndex.best_metric_value.desc(),
                        TaskResultSummaryIndex.result_timestamp.desc(),
                        TaskResultSummaryIndex.id.desc(),
                    ),
                ).label("row_number"),
            )
            .subquery()
        )
        return (
            TaskResultSummaryIndex.query
            .join(subquery, TaskResultSummaryIndex.id == subquery.c.id)
            .filter(subquery.c.row_number == 1)
            .order_by(
                TaskResultSummaryIndex.stock_code.asc(),
                TaskResultSummaryIndex.best_metric_value.desc(),
                TaskResultSummaryIndex.result_timestamp.desc(),
                TaskResultSummaryIndex.id.desc(),
            )
        )

    def _count_index_rows(self, task_type: str | None = None, task_id: str | None = None) -> int:
        query = TaskResultSummaryIndex.query
        if task_id:
            query = query.filter(TaskResultSummaryIndex.task_id == task_id)
        if task_type:
            query = query.filter(TaskResultSummaryIndex.task_type == task_type)
        return query.count()

    def _dedupe_best_per_task(self, task_type: str | None = None, task_id: str | None = None) -> int:
        ranked_query = db.session.query(
            TaskResultSummaryIndex.id.label("id"),
            func.row_number().over(
                partition_by=TaskResultSummaryIndex.task_id,
                order_by=(
                    TaskResultSummaryIndex.best_metric_value.desc(),
                    TaskResultSummaryIndex.result_timestamp.desc(),
                    TaskResultSummaryIndex.id.desc(),
                ),
            ).label("row_number"),
        )
        if task_id:
            ranked_query = ranked_query.filter(TaskResultSummaryIndex.task_id == task_id)
        if task_type:
            ranked_query = ranked_query.filter(TaskResultSummaryIndex.task_type == task_type)
        ranked = ranked_query.subquery()
        duplicate_ids = db.session.query(ranked.c.id).filter(ranked.c.row_number > 1)
        deleted = (
            TaskResultSummaryIndex.query
            .filter(TaskResultSummaryIndex.id.in_(duplicate_ids))
            .delete(synchronize_session=False)
        )
        TaskResultSummaryIndex.query.filter(
            TaskResultSummaryIndex.id.in_(
                db.session.query(ranked.c.id).filter(ranked.c.row_number == 1)
            )
        ).update({"is_best": True}, synchronize_session=False)
        return deleted

    def _keep_only_best_for_task(self, task_id: str) -> None:
        rows = (
            TaskResultSummaryIndex.query
            .filter_by(task_id=task_id)
            .order_by(
                TaskResultSummaryIndex.best_metric_value.desc(),
                TaskResultSummaryIndex.result_timestamp.desc(),
                TaskResultSummaryIndex.id.desc(),
            )
            .all()
        )
        for index, row in enumerate(rows):
            if index == 0 and row.best_metric_value is not None:
                row.is_best = True
                continue
            db.session.delete(row)

    def _update_rebuild_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        current_step: int | None = None,
        total_steps: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        error_message: str | None = None,
        message: str | None = None,
        level: str = "info",
    ) -> None:
        task = db.session.get(Task, task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if current_step is not None:
            task.current_step = current_step
        if total_steps is not None:
            task.total_steps = total_steps
        if start_time is not None:
            task.start_time = start_time
        if end_time is not None:
            task.end_time = end_time
        if error_message is not None:
            task.error_message = error_message
        if message:
            db.session.add(TaskLog(task_id=task_id, level=level, message=message))
        db.session.commit()

    def _job_with_task_status(self, job: dict[str, Any]) -> dict[str, Any]:
        task_id = job.get("task_id") or job.get("job_id")
        task = db.session.get(Task, task_id) if task_id else None
        if task:
            job["task"] = task.to_dict()
            job["status"] = task.status
            if task.status == "completed":
                job["message"] = "索引重建完成"
            elif task.status == "error":
                job["message"] = task.error_message or "索引重建失败"
        return job

    def _job_from_task(self, task_id: str | None) -> dict[str, Any] | None:
        if not task_id:
            return None
        task = db.session.get(Task, task_id)
        if not task or task.task_type != MODEL_SUMMARY_REBUILD_TASK_TYPE:
            return None
        config = _parse_json(task.config, {})
        return {
            "job_id": task.id,
            "task_id": task.id,
            "status": task.status,
            "message": task.error_message or task.status,
            "params": config if isinstance(config, dict) else {},
            "result": None,
            "error": task.error_message,
            "started_at": task.start_time.isoformat() if task.start_time else None,
            "finished_at": task.end_time.isoformat() if task.end_time else None,
            "task": task.to_dict(),
        }

    def _columns_for_task_type(self, task_type: str | None) -> list[dict[str, str]]:
        return BACKTEST_SUMMARY_COLUMNS if normalize_task_type(task_type) == "backtest_training" else SUMMARY_COLUMNS

    def _empty_response(
        self,
        page: int,
        per_page: int,
        columns: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "columns": columns or SUMMARY_COLUMNS,
            "items": [],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": 0,
                "pages": 0,
                "has_prev": False,
                "has_next": False,
            },
        }


model_summary_service = ModelSummaryService()
