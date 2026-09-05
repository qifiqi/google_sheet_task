"""单模型历史结果汇总索引 · 记录抽取与领域词汇（纯函数与常量，无状态）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import has_app_context

from app.models import Task, TaskResult
from app.services.performance_analysis.historical_metrics import upgrade_historical_metrics
from app.services.stock_metadata_service import lookup_stock_metadata
from app.services.xpl_service import xpl_analyzer
from app.utils.market import infer_market_type, normalize_stock_code, strip_stock_code_suffix
from app.utils.task_types import normalize_task_type
from app.utils.value_parser import parse_int, parse_percent_like


SUPPORTED_TASK_TYPES = ("google_sheet", "google_sheet_C4", "google_sheet_C5", "backtest_training")
MODEL_SUMMARY_REBUILD_TASK_TYPE = "model_summary_rebuild"
FINISHED_TASK_STATUSES = ("completed", "cancelled", "error")
ACTIVE_REBUILD_TASK_STATUSES = ("pending", "running")
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
    {"key": "start_sortino_ratio", "label": "模型索提诺比率", "format": "number"},
    {"key": "index_sortino_ratio", "label": "指数索提诺比率", "format": "number"},
    {"key": "excess_sharpe", "label": "超额夏普", "format": "number"},
    {"key": "excess_sortino", "label": "超额索提诺比率", "format": "number"},
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
    ("drawdown_year_max_repair_days", "年最大回测修复天数"),
    ("ratio_sharpe_ratio", "夏普比率"),
    ("ratio_kama_ratio", "卡玛比率"),
    ("ratio_sortino_ratio", "索提诺比率"),
    ("sharpe_excess_sharpe", "超额夏普"),
    ("sortino_excess_sortino_ratio", "超额索提诺比率"),
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

TASK_TYPE_LABELS = {
    "google_sheet": "C3",
    "google_sheet_C4": "C4",
    "google_sheet_C5": "C5",
    "backtest_training": "回测",
}


@dataclass(frozen=True)
class SummaryRecord:
    task_id: str
    task_result_id: int
    task_type: str
    task_name: str
    stock_code: str
    stock_name: str
    model_key: str
    model_name: str
    year_label: str
    period_key: str
    kline_range: str
    parameter_summary: dict[str, Any]
    best_metric_name: str
    best_metric_value: float | None
    metrics: dict[str, Any]
    result_timestamp: datetime | None


def _parse_json(raw: Any, default: Any) -> Any:
    """处理_parse_json相关逻辑。"""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


_safe_number = parse_percent_like


def _fmt_percent_like(value: Any) -> float | None:
    """处理_fmt_percent_like相关逻辑。"""
    return _safe_number(value)


def _normalize_scientific_text(text: str) -> str:
    """处理_normalize_scientific_text相关逻辑。"""
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
    """处理_summary_key_from_label相关逻辑。"""
    text = str(label or "").strip()
    if text in BACKTEST_SUMMARY_KEY_BY_LABEL:
        return BACKTEST_SUMMARY_KEY_BY_LABEL[text]
    slug = re.sub(r"\W+", "_", text.lower(), flags=re.UNICODE).strip("_")
    return f"backtest_{slug}" if slug else ""


def _first_dict_value(payload: Any) -> dict[str, Any]:
    """处理_first_dict_value相关逻辑。"""
    if not isinstance(payload, dict) or not payload:
        return {}
    value = next(iter(payload.values()))
    return value if isinstance(value, dict) else {}


def _all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    """处理_all_entry相关逻辑。"""
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def _kline_range(parameters: Any) -> str:
    """处理_kline_range相关逻辑。"""
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


def _normalize_year_number(value: str) -> int | None:
    """处理_normalize_year_number相关逻辑。"""
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{2}|\d{4}", text):
        return None
    year = parse_int(text)
    if year is None:
        return None
    return 2000 + year if year < 100 else year


def _period_key_from_year_label(value: Any) -> str:
    """处理_period_key_from_year_label相关逻辑。"""
    text = str(value or "").strip()
    if not text:
        return ""

    compact = re.sub(r"\s+", "", text)
    year = _normalize_year_number(compact)
    if year is not None:
        return f"full_{year}"

    match = re.fullmatch(r"(\d{2}|\d{4})[-_/~](\d{2}|\d{4})", compact)
    if not match:
        return ""
    end_year = _normalize_year_number(match.group(1))
    start_year = _normalize_year_number(match.group(2))
    if end_year is None or start_year is None:
        return ""
    diff = abs(end_year - start_year)
    if diff <= 0:
        return ""
    return f"recent_{diff}y"


def _period_key_from_year_n(value: Any) -> str:
    """处理_period_key_from_year_n相关逻辑。"""
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"([13])\s*y", text)
    if not match:
        return ""
    return f"recent_{match.group(1)}y"


def _period_key_from_c3_task_name(task_name: Any) -> str:
    """处理_period_key_from_c3_task_name相关逻辑。"""
    text = _strip_task_name_bracket_content(task_name)
    if not text:
        return ""
    match = re.search(r"(^|[-_\s\(\[（【])([13])y($|[-_\s\)\]）】])", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"recent_{match.group(2).lower()}y"


def _period_key_for_record(task: Task, parameters: Any, year_label: str) -> str:
    """处理_period_key_for_record相关逻辑。"""
    period_key = _period_key_from_year_label(year_label)
    if period_key:
        return period_key

    normalized = normalize_task_type(task.task_type)
    if normalized == "google_sheet":
        config = _parse_json(task.config, {})
        if isinstance(config, dict):
            period_key = _period_key_from_year_n(config.get("year_n"))
            if period_key:
                return period_key
        return _period_key_from_c3_task_name(task.name)

    return ""


def _summary_record_group_key(row: SummaryRecord) -> str:
    """处理_summary_record_group_key相关逻辑。"""
    return row.period_key or row.year_label or row.kline_range or ""


def _json_text(value: Any) -> str:
    """处理_json_text相关逻辑。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def _normalize_market_type(value: Any) -> str:
    """处理_normalize_market_type相关逻辑。"""
    text = str(value or "").strip().lower()
    if text in {"cn", "a", "a股", "ashare", "china"}:
        return "cn"
    if text in {"us", "en", "美股", "usa"}:
        return "us"
    return ""


def _is_cn_stock_code(stock_code: Any) -> bool:
    """处理_is_cn_stock_code相关逻辑。"""
    return bool(re.fullmatch(r"\d+", strip_stock_code_suffix(stock_code)))


def _matches_market_type(stock_code: Any, market_type: str) -> bool:
    """处理_matches_market_type相关逻辑。"""
    if not market_type:
        return True
    text = str(stock_code or "").strip()
    if not text:
        return False
    is_cn = infer_market_type(text) == "cn"
    return is_cn if market_type == "cn" else not is_cn


def _normalize_excess_return_min(value: Any) -> float | None:
    """处理_normalize_excess_return_min相关逻辑。"""
    if value in (None, ""):
        return None
    number = _safe_number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def _parameter_summary(parameters: Any) -> dict[str, Any]:
    """处理_parameter_summary相关逻辑。"""
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
    """处理_first_text_value相关逻辑。"""
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _display_model_name(raw_name: Any, task_type: str | None = None) -> str:
    """处理_display_model_name相关逻辑。"""
    text = str(raw_name or "").strip()
    lower_text = text.lower()
    normalized = normalize_task_type(task_type)
    if "c5" in lower_text or normalized == "google_sheet_c5":
        return "C5"
    if "c4" in lower_text or normalized == "google_sheet_c4":
        return "C4"
    return text


def _strip_task_name_bracket_content(value: Any) -> str:
    """处理_strip_task_name_bracket_content相关逻辑。"""
    text = str(value or "").strip()
    if not text:
        return ""
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\s*[\(（][^()（）]*[\)）]\s*", " ", text).strip()
        text = re.sub(r"\s*[\[【][^\[\]【】]*[\]】]\s*", " ", text).strip()
    return re.sub(r"\s+", " ", text).strip()


def _stock_code_from_task_name(task_type: str | None, task_name: str | None) -> str:
    """处理_stock_code_from_task_name相关逻辑。"""
    text = _strip_task_name_bracket_content(task_name)
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
    """处理_extract_stock_code相关逻辑。"""
    normalized = normalize_task_type(task.task_type)
    parameter_task_name = _first_text_value(
        parameters,
        ("task_name", "name", "base_task_name", "taskName"),
    )

    config = _parse_json(task.config, {})

    def standardize(value: Any) -> str:
        """处理standardize相关逻辑。"""
        market_type = config.get("market_type") if isinstance(config, dict) else None
        return normalize_stock_code(value, market_type or infer_market_type(value))

    if isinstance(parameters, dict):
        direct = _first_text_value(parameters, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return standardize(direct)
        config_from_parameters = parameters.get("config")
        if isinstance(config_from_parameters, dict):
            config = {**config, **config_from_parameters} if isinstance(config, dict) else config_from_parameters

    parsed = _stock_code_from_task_name(task.task_type, parameter_task_name)
    if parsed:
        return standardize(parsed)

    if isinstance(config, dict):
        direct = _first_text_value(config, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return standardize(direct)
        parsed = _stock_code_from_task_name(
            task.task_type,
            _first_text_value(config, ("task_name", "name", "base_task_name", "taskName")),
        )
        if parsed:
            return standardize(parsed)

    parsed = _stock_code_from_task_name(task.task_type, task.name)
    if parsed:
        return standardize(parsed)

    direct = _first_text_value(parameters, ("stock_code", "stock_no", "code", "symbol"))
    if direct:
        return standardize(direct)
    if isinstance(config, dict):
        direct = _first_text_value(config, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return standardize(direct)
    return str(task.id).strip().upper()


def _extract_stock_name(parameters: Any) -> str:
    """处理_extract_stock_name相关逻辑。"""
    if not isinstance(parameters, dict):
        return ""
    return _first_text_value(parameters, ("stock_name", "name_cn", "product_name"))


def _stock_name_from_config(task: Task, parameters: Any, stock_code: str) -> str:
    """处理_stock_name_from_config相关逻辑。"""
    stock_name = _extract_stock_name(parameters)
    if stock_name:
        return stock_name

    config = _parse_json(task.config, {})
    if isinstance(config, dict):
        stock_name = _first_text_value(config, ("stock_name", "name_cn", "product_name"))
        if stock_name:
            return stock_name
        if not has_app_context():
            return ""
        metadata = lookup_stock_metadata(stock_code, config.get("market_type"))
    else:
        if not has_app_context():
            return ""
        metadata = lookup_stock_metadata(stock_code)
    return str(metadata.get("stock_name") or "").strip()


def _extract_candidate_records(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """处理_extract_candidate_records相关逻辑。"""
    return [
        row
        for row in extract_summary_records(task, result)
        if row.best_metric_value is not None
    ]


def _extract_return_analysis_metrics(payload: dict[str, Any]) -> dict[str, float]:
    """处理_extract_return_analysis_metrics相关逻辑。"""
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
        "start_sortino_ratio": "start_sortino_ratio",
        "index_sortino_ratio": "index_sortino_ratio",
        "excess_sharpe": "excess_sharpe",
        "excess_sortino": "excess_sortino",
    }
    metrics = {}
    for output_key, source_key in field_map.items():
        value = _safe_number(payload.get(source_key))
        if value is not None:
            metrics[output_key] = value
    return metrics


def _first_safe_number(*values: Any) -> float | None:
    """处理_first_safe_number相关逻辑。"""
    for value in values:
        number = _safe_number(value)
        if number is not None:
            return number
    return None


def _extract_c3(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """处理_extract_c3相关逻辑。"""
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
    stock_code = _extract_stock_code(task, parameters)
    year_label = str(summary.get("year") or "")
    kline_range = _kline_range({"kline": parameters[-1]} if isinstance(parameters, list) and parameters else parameters)
    return [
        SummaryRecord(
            task_id=task.id,
            task_result_id=result.id,
            task_type=task.task_type,
            task_name=task.name,
            stock_code=stock_code,
            stock_name=_stock_name_from_config(task, parameters, stock_code),
            model_key="default",
            model_name="C3",
            year_label=year_label,
            period_key=_period_key_for_record(task, parameters, year_label),
            kline_range=kline_range,
            parameter_summary=summary,
            best_metric_name="ReturnBeats",
            best_metric_value=return_beats,
            metrics={key: value for key, value in metrics.items() if value is not None},
            result_timestamp=result.timestamp,
        )
    ]


def _extract_c4_c5(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """处理_extract_c4_c5相关逻辑。"""
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
        stock_code = _extract_stock_code(task, parameters)
        year_label = str(parameters.get("year") or parameters.get("Kline_key") or "")
        records.append(
            SummaryRecord(
                task_id=task.id,
                task_result_id=result.id,
                task_type=task.task_type,
                task_name=task.name,
                stock_code=stock_code,
                stock_name=_stock_name_from_config(task, parameters, stock_code),
                model_key=str(model_key),
                model_name=model_name,
                year_label=year_label,
                period_key=_period_key_for_record(task, parameters, year_label),
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
    """处理_extract_c5相关逻辑。"""
    return _extract_c4_c5(task, result)


def _format_backtest_percent(value: Any) -> str:
    """处理_format_backtest_percent相关逻辑。"""
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2%}"


def _format_backtest_number(value: Any) -> str:
    """处理_format_backtest_number相关逻辑。"""
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _negative_number(value: Any) -> float | None:
    """处理_negative_number相关逻辑。"""
    number = _safe_number(value)
    return -number if number is not None else None


def _normalize_backtest_display_value(value: Any) -> str:
    """处理_normalize_backtest_display_value相关逻辑。"""
    text = str(value or "").strip()
    if not text:
        return ""
    while text.startswith("--"):
        text = text[1:]
    return _normalize_scientific_text(text)


def _max_yearly_repair_days(yearly_repair_days: Any) -> float | None:
    """处理_max_yearly_repair_days相关逻辑。"""
    if not isinstance(yearly_repair_days, dict):
        return None
    values = [
        number
        for value in yearly_repair_days.values()
        for number in [_safe_number(value)]
        if number is not None
    ]
    return max(values) if values else None


def _format_backtest_repair_days(value: Any) -> str:
    """处理_format_backtest_repair_days相关逻辑。"""
    number = _safe_number(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def _extract_backtest_metric_values(calculate_metrics: dict[str, Any]) -> dict[str, str]:
    """处理_extract_backtest_metric_values相关逻辑。"""
    excess_all = _all_entry(calculate_metrics.get("excess_returns"))
    index_profit_monthly_all = _all_entry(calculate_metrics.get("index_profit_monthly"))
    start_profit_monthly_all = _all_entry(calculate_metrics.get("start_profit_monthly"))
    start_kama_all = _all_entry(calculate_metrics.get("start_kama_ratio"))
    start_sortino_all = _all_entry(calculate_metrics.get("start_sortino_ratio"))
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
    year_start_max_repair_days = _max_yearly_repair_days(
        calculate_metrics.get("year_start_yearly_max_repair_days")
    )
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
        "drawdown_year_max_repair_days": _format_backtest_repair_days(year_start_max_repair_days),
        "ratio_sharpe_ratio": _format_backtest_number(start_sharpe_all.get("sharpe_ratio")),
        "ratio_kama_ratio": _format_backtest_number(start_kama_all.get("kama_ratio")),
        "ratio_sortino_ratio": _format_backtest_number(start_sortino_all.get("sortino_ratio")),
        "sharpe_excess_sharpe": _format_backtest_number(calculate_metrics.get("excess_sharpe")),
        "sortino_excess_sortino_ratio": _format_backtest_number(calculate_metrics.get("excess_sortino")),
    }


def _extract_backtest_summary_rows(calculate_metrics: dict[str, Any], model_name: str) -> tuple[str, list[dict[str, str]]]:
    """处理_extract_backtest_summary_rows相关逻辑。"""
    def _safe_all_entry(items: Any) -> dict[str, Any]:
        """处理_safe_all_entry相关逻辑。"""
        return _all_entry(items, "year")

    def _fallback_rows() -> tuple[str, list[dict[str, str]]]:
        """处理_fallback_rows相关逻辑。"""
        excess_all = _safe_all_entry(calculate_metrics.get("excess_returns"))
        index_profit_monthly_all = _safe_all_entry(calculate_metrics.get("index_profit_monthly"))
        start_profit_monthly_all = _safe_all_entry(calculate_metrics.get("start_profit_monthly"))
        index_kama_all = _safe_all_entry(calculate_metrics.get("index_kama_ratio"))
        start_kama_all = _safe_all_entry(calculate_metrics.get("start_kama_ratio"))
        index_sortino_all = _safe_all_entry(calculate_metrics.get("index_sortino_ratio"))
        start_sortino_all = _safe_all_entry(calculate_metrics.get("start_sortino_ratio"))
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
        year_start_max_repair_days = _max_yearly_repair_days(
            calculate_metrics.get("year_start_yearly_max_repair_days")
        )
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
            ("年最大回测修复天数", _format_backtest_repair_days(year_start_max_repair_days)),
            ("夏普比率", _format_backtest_number(start_sharpe_all.get("sharpe_ratio"))),
            ("卡玛比率", _format_backtest_number(start_kama_all.get("kama_ratio"))),
            ("索提诺比率", _format_backtest_number(start_sortino_all.get("sortino_ratio"))),
            ("超额夏普", _format_backtest_number(calculate_metrics.get("excess_sharpe"))),
            ("超额索提诺比率", _format_backtest_number(calculate_metrics.get("excess_sortino"))),
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
    for row_index in range(3, 3 + len(BACKTEST_SUMMARY_METRICS)):
        metric = str(summary_df.iat[row_index, 1] or "").strip()
        if not metric:
            continue
        rows.append({
            "metric": metric,
            "model_value": _normalize_backtest_display_value(summary_df.iat[row_index, 3]),
        })
    return period_text, rows


def _extract_backtest(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """处理_extract_backtest相关逻辑。"""
    parameters = _parse_json(result.parameters, {})
    payload = _parse_json(result.result, {})
    core = _first_dict_value(payload)
    if isinstance(core, dict) and isinstance(core.get("metrics_payload"), dict):
        # 统一存储契约：{schema_version, metrics, canonical_metrics}。
        calculate_metrics = core["metrics_payload"].get("metrics")
    else:
        # TODO: 数据库历史 TaskResult 仍保存 calculate_metrics 旧键，迁移后移除回退。
        calculate_metrics = core.get("calculate_metrics") if isinstance(core, dict) else {}
    calculate_metrics = calculate_metrics if isinstance(calculate_metrics, dict) else {}
    if calculate_metrics:
        # TODO: 历史载荷字段名（sotino/cumulative_excess 等）迁移后移除该升级。
        calculate_metrics = upgrade_historical_metrics(calculate_metrics)
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
    stock_code = _extract_stock_code(task, parameters)
    year_label = str(parameters.get("year") or parameters.get("Kline_key") or "")
    return [
        SummaryRecord(
            task_id=task.id,
            task_result_id=result.id,
            task_type=task.task_type,
            task_name=task.name,
            stock_code=stock_code,
            stock_name=_stock_name_from_config(task, parameters, stock_code),
            model_key="default",
            model_name="回测",
            year_label=year_label,
            period_key=_period_key_for_record(task, parameters, year_label),
            kline_range=period_text or _kline_range(parameters),
            parameter_summary=_parameter_summary(parameters),
            best_metric_name="年化超额收益",
            best_metric_value=annualized_diff,
            metrics={key: value for key, value in metrics.items() if value not in (None, "")},
            result_timestamp=result.timestamp,
        )
    ]


def extract_summary_records(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """处理extract_summary_records相关逻辑。"""
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
