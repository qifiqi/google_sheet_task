"""单模型历史结果汇总索引服务。"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import has_app_context

from app.repositories.task_result_summary_index_repository import TaskResultSummaryIndexRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.services.stock_metadata_service import lookup_stock_metadata
from app.services.xpl_service import xpl_analyzer
from app.utils.logger import get_logger
from app.utils.task_authorization import filter_task_types_by_action, normalize_task_type


logger = get_logger(__name__)
_summary_index_repository = TaskResultSummaryIndexRepository()
_task_log_repository = TaskLogRepository()
_task_repository = TaskRepository()
_task_result_repository = TaskResultRepository()

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
    ("drawdown_year_max_repair_days", "年最大回测修复天数"),
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

CSV_LEADING_COLUMNS = [
    ("stock_code", "产品/股票"),
    ("stock_name", "股票名"),
    ("task_name", "任务名"),
    ("task_type", "类型"),
    ("best_metric_value", "return beats"),
    ("result_timestamp", "结果时间"),
]

CSV_TRAILING_COLUMNS = [
    ("task_result_id", "结果 ID"),
]

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
    """安全解析远端 JSON 字段，无法解析时返回调用方默认值。"""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _parse_result_timestamp(value: Any) -> datetime | None:
    """把 TaskResult HTTP 返回的时间文本转换为汇总计算使用的时间对象。"""
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _safe_number(value: Any) -> float | None:
    """将文本、百分比或数字转换为有限浮点数。"""
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
    """兼容百分比格式的数值解析入口。"""
    return _safe_number(value)


def _normalize_scientific_text(text: str) -> str:
    """将科学计数法文本展开为可读的普通数值字符串。"""
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
    """将展示指标名称映射为稳定的汇总字段键。"""
    text = str(label or "").strip()
    if text in BACKTEST_SUMMARY_KEY_BY_LABEL:
        return BACKTEST_SUMMARY_KEY_BY_LABEL[text]
    slug = re.sub(r"\W+", "_", text.lower(), flags=re.UNICODE).strip("_")
    return f"backtest_{slug}" if slug else ""


def _first_dict_value(payload: Any) -> dict[str, Any]:
    """从嵌套结果载荷中取得首个字典对象。"""
    if not isinstance(payload, dict) or not payload:
        return {}
    value = next(iter(payload.values()))
    return value if isinstance(value, dict) else {}


def _all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    """从年度或周期指标列表中获取 all 聚合项。"""
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def _kline_range(parameters: Any) -> str:
    """从参数 K 线列表提取起止日期展示范围。"""
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
    """规范化两位或四位年份文本为四位年份整数。"""
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{2}|\d{4}", text):
        return None
    year = int(text)
    return 2000 + year if year < 100 else year


def _period_key_from_year_label(value: Any) -> str:
    """从年份或年份区间标签推导统一周期键。"""
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
    """从 C3 的年数配置推导最近 N 年周期键。"""
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"([13])\s*y", text)
    if not match:
        return ""
    return f"recent_{match.group(1)}y"


def _period_key_from_c3_task_name(task_name: Any) -> str:
    """从 C3 任务名称中提取 1y 或 3y 周期标识。"""
    text = _strip_task_name_bracket_content(task_name)
    if not text:
        return ""
    match = re.search(r"(^|[-_\s\(\[（【])([13])y($|[-_\s\)\]）】])", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"recent_{match.group(2).lower()}y"


def _period_key_for_record(task: Task, parameters: Any, year_label: str) -> str:
    """按结果标签、任务配置和名称优先级确定汇总分组周期。"""
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
    """返回汇总记录用于分组的最优周期标识。"""
    return row.period_key or row.year_label or row.kline_range or ""


def _json_text(value: Any) -> str:
    """以 UTF-8 友好的方式序列化任意值用于远端 JSON 字段。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def _csv_text(value: Any) -> str:
    """将标量或结构化值转换为 CSV 单元格文本。"""
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return str(value)


def _format_csv_metric(value: Any, format_name: str | None = None) -> str:
    """按字段格式输出 CSV 指标文本。"""
    if value in (None, ""):
        return ""
    if not format_name and isinstance(value, str):
        return value
    number = _safe_number(value)
    if number is None:
        return _csv_text(value)
    if format_name == "percent":
        return f"{number * 100:.2f}%"
    if format_name == "integer":
        return str(int(round(number)))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _format_csv_parameter_summary(value: Any) -> str:
    """将参数摘要压缩为 CSV 中易读的逗号分隔文本。"""
    if isinstance(value, dict):
        parameter_value = value.get("parameter")
        if isinstance(parameter_value, list):
            return ",".join(_csv_text(item) for item in parameter_value)
        a1 = value.get("A1")
        b1 = value.get("B1")
        if a1 not in (None, "") or b1 not in (None, ""):
            return ",".join(_csv_text(item) for item in (a1, b1) if item not in (None, ""))
        return _csv_text(parameter_value)

    parameter_value = value
    if isinstance(parameter_value, list):
        return ",".join(_csv_text(item) for item in parameter_value)
    return _csv_text(parameter_value)


def _interval_display_value(item: dict[str, Any]) -> str:
    """优先返回 K 线范围，其次返回年度标签作为区间展示。"""
    return _csv_text(item.get("kline_range") or item.get("year_label"))


def _normalize_market_type(value: Any) -> str:
    """将多种市场别名归一为 cn、us 或空值。"""
    text = str(value or "").strip().lower()
    if text in {"cn", "a", "a股", "ashare", "china"}:
        return "cn"
    if text in {"us", "en", "美股", "usa"}:
        return "us"
    return ""


def _is_cn_stock_code(stock_code: Any) -> bool:
    """通过纯数字代码规则识别 A 股股票代码。"""
    return bool(re.fullmatch(r"\d+", str(stock_code or "").strip()))


def _matches_market_type(stock_code: Any, market_type: str) -> bool:
    """判断股票代码是否符合指定市场筛选条件。"""
    if not market_type:
        return True
    text = str(stock_code or "").strip()
    if not text:
        return False
    is_cn = _is_cn_stock_code(text)
    return is_cn if market_type == "cn" else not is_cn


def _normalize_excess_return_min(value: Any) -> float | None:
    """把页面超额收益阈值统一转换为小数形式。"""
    if value in (None, ""):
        return None
    number = _safe_number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def _parameter_summary(parameters: Any) -> dict[str, Any]:
    """从不同任务参数结构提取用于汇总展示的简要字段。"""
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
    """按候选字段顺序读取第一个非空文本值。"""
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _display_model_name(raw_name: Any, task_type: str | None = None) -> str:
    """规范化模型展示名，兼容任务类型与名称中的 C4/C5 标识。"""
    text = str(raw_name or "").strip()
    lower_text = text.lower()
    normalized = normalize_task_type(task_type)
    if "c5" in lower_text or normalized == "google_sheet_c5":
        return "C5"
    if "c4" in lower_text or normalized == "google_sheet_c4":
        return "C4"
    return text


def _strip_task_name_bracket_content(value: Any) -> str:
    """移除任务名中的中英文括号备注，保留可解析主体。"""
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
    """按任务类型和命名规则从任务名回退解析股票代码。"""
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
    """按参数、配置与任务名优先级提取任务关联股票代码。"""
    normalized = normalize_task_type(task.task_type)
    parameter_task_name = _first_text_value(
        parameters,
        ("task_name", "name", "base_task_name", "taskName"),
    )

    config = _parse_json(task.config, {})
    if isinstance(parameters, dict):
        direct = _first_text_value(parameters, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return direct.upper()
        config_from_parameters = parameters.get("config")
        if isinstance(config_from_parameters, dict):
            config = {**config, **config_from_parameters} if isinstance(config, dict) else config_from_parameters

    parsed = _stock_code_from_task_name(task.task_type, parameter_task_name)
    if parsed:
        return parsed

    if isinstance(config, dict):
        direct = _first_text_value(config, ("stock_code", "stock_no", "code", "symbol"))
        if direct:
            return direct.upper()
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


def _extract_stock_name(parameters: Any) -> str:
    """从结果参数中读取可用的股票中文名称。"""
    if not isinstance(parameters, dict):
        return ""
    return _first_text_value(parameters, ("stock_name", "name_cn", "product_name"))


def _stock_name_from_config(task: Task, parameters: Any, stock_code: str) -> str:
    """从参数、任务配置或元数据缓存中补充股票名称。"""
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
    """提取包含可比较最佳指标的候选汇总记录。"""
    return [
        row
        for row in extract_summary_records(task, result)
        if row.best_metric_value is not None
    ]


def _extract_return_analysis_metrics(payload: dict[str, Any]) -> dict[str, float]:
    """从收益分析载荷中抽取扁平化的标准指标集合。"""
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
    """依次解析候选值并返回第一个有效数值。"""
    for value in values:
        number = _safe_number(value)
        if number is not None:
            return number
    return None


def _extract_c3(task: Task, result: TaskResult) -> list[SummaryRecord]:
    """将 C3 单条结果转换为统一的汇总索引记录。"""
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
    """将 C4/C5 多模型结果拆分为独立汇总索引记录。"""
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
    """复用 C4/C5 的通用结果提取流程处理 C5。"""
    return _extract_c4_c5(task, result)


def _format_backtest_percent(value: Any) -> str:
    """将回测指标格式化为两位小数百分比。"""
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2%}"


def _format_backtest_number(value: Any) -> str:
    """将回测数值格式化为去除尾随零的普通文本。"""
    number = _safe_number(value)
    if number is None:
        return ""
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _negative_number(value: Any) -> float | None:
    """将有效数值转换为负值，供回撤类指标统一展示。"""
    number = _safe_number(value)
    return -number if number is not None else None


def _normalize_backtest_display_value(value: Any) -> str:
    """清理回测导出中的占位前缀并展开科学计数法。"""
    text = str(value or "").strip()
    if not text:
        return ""
    while text.startswith("--"):
        text = text[1:]
    return _normalize_scientific_text(text)


def _max_yearly_repair_days(yearly_repair_days: Any) -> float | None:
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
    number = _safe_number(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def _extract_backtest_metric_values(calculate_metrics: dict[str, Any]) -> dict[str, str]:
    """从回测计算指标生成固定列集合的展示值。"""
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
        "ratio_sortino_ratio": _format_backtest_number(start_sotino_all.get("sotino_ratio")),
        "sharpe_excess_sharpe": _format_backtest_number(calculate_metrics.get("excess_sharp")),
        "sortino_excess_sortino_ratio": _format_backtest_number(calculate_metrics.get("excess_of_promissory_note")),
    }


def _extract_backtest_summary_rows(calculate_metrics: dict[str, Any], model_name: str) -> tuple[str, list[dict[str, str]]]:
    """优先经 XPL 格式化生成回测摘要，失败时回退本地指标映射。"""
    def _safe_all_entry(items: Any) -> dict[str, Any]:
        """读取当前计算指标中的年度 all 聚合项。"""
        return _all_entry(items, "year")

    def _fallback_rows() -> tuple[str, list[dict[str, str]]]:
        """在 XPL 格式化失败时从原始计算指标构造摘要行。"""
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
    """将单品回测结果转换为统一汇总索引记录。"""
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
    """按任务类型提炼成功结果，用于构建统一的汇总索引记录。"""
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
        """初始化索引重建作业缓存、作业锁和索引写入锁。"""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._index_lock = threading.RLock()

    def upsert_task_result(self, task_result_id: int, *, commit: bool = True) -> int:
        """串行更新单条任务结果对应的汇总索引，避免并发写入互相覆盖。"""
        with self._index_lock:
            return self._upsert_task_result_locked(task_result_id, commit=commit)

    def upsert_task(self, task_id: str, *, commit: bool = True) -> dict[str, int]:
        """从单个任务的全部成功结果重建汇总索引行。"""
        if not task_id:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}
        with self._index_lock:
            summary = self._upsert_task_batch([task_id])
            # 远程 CRUD 已逐条提交；保留参数以兼容旧调用方。
            return summary

    @staticmethod
    def _list_summary_indexes(**filters: Any) -> list[dict[str, Any]]:
        """分页读取远程汇总索引，删除和去重前先收集完整数据。"""
        page_index = 1
        records: list[dict[str, Any]] = []
        while True:
            page = _summary_index_repository.list_indexes(
                page_index=page_index,
                page_size=200,
                **filters,
            )
            items = page["items"]
            records.extend(items)
            if not items or page_index * 200 >= page["total"]:
                return records
            page_index += 1

    def _upsert_task_result_locked(self, task_result_id: int, *, commit: bool = True) -> int:
        """在索引锁内同步单条结果对应的汇总记录并清理过期模型键。"""
        result = _task_result_repository.get(int(task_result_id))
        if not result:
            return 0
        task = _task_repository.get(result.get("task_id"))
        if not task:
            return 0
        result.timestamp = _parse_result_timestamp(result.get("timestamp"))
        rows = _extract_candidate_records(task, result)
        existing = {
            str(item.get("model_key") or ""): item
            for item in self._list_summary_indexes(task_result_id=int(task_result_id))
        }
        changed_task_ids = set()
        for row in rows:
            item = existing.get(row.model_key)
            _summary_index_repository.save(self._summary_index_payload(
                row,
                record_id=item.get("id") if item else None,
                is_best=bool(item.get("is_best")) if item else False,
            ))
            changed_task_ids.add(row.task_id)

        stale_keys = set(existing) - {row.model_key for row in rows}
        for key in stale_keys:
            changed_task_ids.add(str(existing[key].get("task_id") or ""))
            _summary_index_repository.delete(int(existing[key]["id"]))

        for changed_task_id in changed_task_ids:
            if changed_task_id:
                self._keep_only_best_for_task(changed_task_id)
        # 远程 CRUD 已逐条提交；保留参数以兼容旧调用方。
        return len(rows)

    def rebuild(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
        batch_size: int = 20,
        reset: bool = False,
        progress_task_id: str | None = None,
    ) -> dict[str, int]:
        """按筛选条件批量重建汇总索引，并通过进度任务反馈执行状态。"""
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
        """按筛选条件执行索引重建、可选清空和每任务最优记录去重。"""
        if reset:
            reset_items = self._list_summary_indexes(task_id=task_id, task_type=task_type)
            reset_ids = [int(item["id"]) for item in reset_items if item.get("id") is not None]
            for index_id in reset_ids:
                _summary_index_repository.delete(index_id)
            deleted = len(reset_ids)
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

        deduped = self._dedupe_best_per_task(task_type=task_type, task_id=task_id)
        indexed = self._count_index_rows(task_type=task_type, task_id=task_id)
        if progress_task_id:
            self._update_rebuild_task(
                progress_task_id,
                current_step=processed_tasks,
                total_steps=total,
                message=f"索引表当前保留 {indexed} 条任务/时间分组最优记录，去重删除 {deduped} 条",
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
        """创建后台索引重建任务；同时只允许一个重建作业处于活跃状态。"""
        with self._jobs_lock:
            active_job = self._active_rebuild_job()
            if active_job:
                return active_job

            job_id = str(uuid.uuid4())
            rebuild_task = _task_repository.save({
                "id": job_id,
                "name": "单模型汇总索引重建",
                "description": "后台扫描历史 task_results，重建任务/股票汇总查询索引",
                "task_type": MODEL_SUMMARY_REBUILD_TASK_TYPE,
                "status": "pending",
                "config": {
                    "task_type": task_type,
                    "task_id": task_id,
                    "batch_size": batch_size,
                    "reset": reset,
                },
                "total_steps": 0,
                "current_step": 0,
                "created_by_user_id": created_by_user_id,
            })
            _task_log_repository.save({
                "task_id": job_id,
                "level": "info",
                "message": "索引重建任务已创建",
            })

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
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_rebuild_job,
            args=(app, job_id),
            daemon=True,
            name=f"model-summary-rebuild-{job_id[:8]}",
        )
        thread.start()
        return job.copy()

    def _active_rebuild_job(self) -> dict[str, Any] | None:
        """通过 HTTP 查询当前仍处于待执行或执行中的索引重建作业。"""
        tasks = _task_repository.list_tasks(
            page_size=1,
            task_types=[MODEL_SUMMARY_REBUILD_TASK_TYPE],
            statuses=list(ACTIVE_REBUILD_TASK_STATUSES),
            order_field="created_at",
            order_type="desc",
        )["items"]
        task = tasks[0] if tasks else None
        if not task:
            return None

        job = self._job_from_task(task.get("id"))
        if job:
            job["message"] = f"已有索引重建任务正在执行: {task.get('id')}"
        return job

    def get_rebuild_job(self, job_id: str) -> dict[str, Any] | None:
        """优先从进程内缓存读取作业，再回退到持久化任务记录。"""
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                return self._job_with_task_status(dict(job))
        return self._job_from_task(job_id)

    def latest_rebuild_job(self) -> dict[str, Any] | None:
        """返回最近一次索引重建作业，支持服务重启后的记录回溯。"""
        with self._jobs_lock:
            if not self._jobs:
                tasks = _task_repository.list_tasks(
                    page_size=1,
                    task_types=[MODEL_SUMMARY_REBUILD_TASK_TYPE],
                    order_field="created_at",
                    order_type="desc",
                )["items"]
                return self._job_from_task(tasks[0].get("id")) if tasks else None
            job = max(self._jobs.values(), key=lambda item: item.get("started_at") or "")
            return self._job_with_task_status(dict(job))

    def _run_rebuild_job(self, app, job_id: str) -> None:
        """在线程中执行重建任务，并同步内存与持久化进度状态。"""
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
                        f"保留 {result.get('indexed', 0)} 条任务/时间分组最优索引，"
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
        """通过远端汇总接口完成筛选、去重、排序、聚合和分页。"""
        page = max(int(filters.get("page") or 1), 1)
        per_page = min(max(int(filters.get("per_page") or 50), 1), 200)
        task_type = str(filters.get("task_type") or "").strip()
        stock_keyword = str(filters.get("stock_code") or "").strip()
        market_type = _normalize_market_type(filters.get("market_type"))
        period_key = str(filters.get("period_filter") or "").strip()
        best_only = str(filters.get("best_only", "true")).lower() not in {"false", "0", "no"}
        summary_type = str(filters.get("summary_type") or "task").strip().lower()
        if summary_type not in {"task", "stock"}:
            summary_type = "task"

        allowed_types = filter_task_types_by_action(user, "view", SUPPORTED_TASK_TYPES)
        if not allowed_types:
            return self._empty_response(page, per_page)
        if task_type:
            if task_type not in allowed_types:
                return self._empty_response(page, per_page, columns=self._columns_for_task_type(task_type))
            visible_types = [task_type]
        else:
            visible_types = [
                item for item in allowed_types
                if normalize_task_type(item) != "backtest_training"
            ]
            if not visible_types:
                return self._empty_response(page, per_page)

        result_timestamp_from = self._parse_filter_date(filters.get("result_date_from"))
        result_timestamp_to = self._parse_filter_date(filters.get("result_date_to"), end_of_day=True)
        result_id = filters.get("result_id")
        try:
            task_result_id = int(result_id) if result_id else None
        except (TypeError, ValueError):
            task_result_id = None

        remote = _summary_index_repository.get_data_summary(
            page_index=page,
            page_size=per_page,
            task_type=task_type or None,
            task_types=visible_types,
            stock_keyword=stock_keyword or None,
            market_type=market_type or None,
            period_key=period_key or None,
            is_best=True if summary_type == "stock" else None,
            best_only=best_only,
            summary_type=summary_type,
            best_metric_value_gt=_normalize_excess_return_min(filters.get("excess_return_min")),
            result_timestamp_from=result_timestamp_from,
            result_timestamp_to=result_timestamp_to,
            task_id=str(filters.get("task_id") or "").strip() or None,
            task_result_id=task_result_id,
        )
        total = int(remote["total"])
        pages = math.ceil(total / per_page) if total else 0
        return {
            "status": "success",
            "summary_type": remote["summary_type"],
            "columns": self._columns_for_task_type(task_type),
            "summary": remote["summary"],
            "items": remote["items"],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
                "has_prev": page > 1,
                "has_next": page < pages,
            },
        }

    @staticmethod
    def _parse_filter_date(value: Any, *, end_of_day: bool = False) -> str | None:
        """将页面日期转换为远端查询使用的 ISO 时间；无效值保持忽略语义。"""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed.isoformat()

    def export_csv(self, user: Any, filters: dict[str, Any]) -> dict[str, Any]:
        """复用分页查询逐页收集可见结果，并生成 CSV 导出内容。"""
        export_filters = dict(filters)
        export_filters["page"] = 1
        export_filters["per_page"] = 200
        items: list[dict[str, Any]] = []
        columns: list[dict[str, str]] = []
        summary_type = str(export_filters.get("summary_type") or "task").strip().lower() or "task"

        while True:
            payload = self.query(user, export_filters)
            if payload.get("status") != "success":
                return payload

            if not columns:
                columns = payload.get("columns") or []
            items.extend(payload.get("items") or [])

            pagination = payload.get("pagination") or {}
            if not pagination.get("has_next"):
                break
            export_filters["page"] = int(export_filters["page"]) + 1

        return {
            "status": "success",
            "filename": self._export_filename(export_filters, summary_type),
            "content": self._render_csv(columns, items),
            "count": len(items),
        }

    def _summary_index_payload(
        self,
        row: SummaryRecord,
        *,
        record_id: int | None = None,
        is_best: bool = False,
    ) -> dict[str, Any]:
        """构造远程汇总索引 CRUD 所需的普通字典。"""
        return {
            "id": record_id,
            "task_id": row.task_id,
            "task_result_id": row.task_result_id,
            "task_type": row.task_type,
            "task_name": row.task_name,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "market_type": "cn" if _is_cn_stock_code(row.stock_code) else "us",
            "model_key": row.model_key,
            "model_name": row.model_name,
            "year_label": row.year_label,
            "period_key": row.period_key,
            "kline_range": row.kline_range,
            "parameter_summary": row.parameter_summary,
            "best_metric_name": row.best_metric_name,
            "best_metric_value": row.best_metric_value,
            "metrics_json": row.metrics,
            "is_best": is_best,
            "result_timestamp": row.result_timestamp,
        }

    def _record_to_dict(self, row: SummaryRecord) -> dict[str, Any]:
        """将内部汇总记录转换为页面与 CSV 共用的字典 DTO。"""
        return {
            "id": None,
            "task_id": row.task_id,
            "task_result_id": row.task_result_id,
            "task_type": row.task_type,
            "task_name": row.task_name,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "model_key": row.model_key,
            "model_name": row.model_name,
            "year_label": row.year_label,
            "period_key": row.period_key,
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

    def _upsert_batch(self, batch: list[tuple[Task, TaskResult]]) -> int:
        """同步一批结果的汇总索引，并删除不再存在的模型键。"""
        changed_task_ids = set()
        indexed = 0

        for task, result in batch:
            rows = _extract_candidate_records(task, result)
            indexed += len(rows)
            existing = {
                str(item.get("model_key") or ""): item
                for item in self._list_summary_indexes(task_result_id=int(result.id))
            }
            for row in rows:
                item = existing.pop(row.model_key, None)
                _summary_index_repository.save(self._summary_index_payload(
                    row,
                    record_id=item.get("id") if item else None,
                    is_best=bool(item.get("is_best")) if item else False,
                ))
                changed_task_ids.add(row.task_id)
            for item in existing.values():
                if item.get("id") is not None:
                    changed_task_ids.add(str(item.get("task_id") or ""))
                    _summary_index_repository.delete(int(item["id"]))

        for changed_task_id in changed_task_ids:
            if changed_task_id:
                self._keep_only_best_for_task(changed_task_id)
        return indexed

    def _load_rebuild_task_ids(
        self,
        task_type: str | None = None,
        task_id: str | None = None,
    ) -> list[str]:
        """通过 ParamTasks 读取符合重建条件且已经结束的任务 ID 列表。"""
        if task_id:
            task = _task_repository.get(task_id)
            return [str(task_id)] if task and task.get("status") in FINISHED_TASK_STATUSES else []
        page_index = 1
        task_ids: list[str] = []
        while True:
            page = _task_repository.list_tasks(
                page_index=page_index,
                page_size=200,
                task_types=[task_type] if task_type else list(SUPPORTED_TASK_TYPES),
                statuses=list(FINISHED_TASK_STATUSES),
                order_field="created_at",
                order_type="asc",
            )
            task_ids.extend(str(item["id"]) for item in page["items"] if item.get("id"))
            if not page["items"] or page_index * 200 >= page["total"]:
                return task_ids
            page_index += 1

    def _upsert_task_batch(self, task_ids: list[str]) -> dict[str, int]:
        """重建一组任务的索引，只保留每任务/周期的最佳候选记录。"""
        if not task_ids:
            return {"processed": 0, "processed_tasks": 0, "candidate_records": 0}

        best_by_group: dict[tuple[str, str], SummaryRecord] = {}
        candidate_records = 0
        processed = 0

        for task_id in task_ids:
            task = _task_repository.get(task_id)
            if not task:
                continue
            results = self._list_task_results(task_id)
            processed += len(results)
            for result in results:
                if not result.get("success"):
                    continue
                result.timestamp = _parse_result_timestamp(result.get("timestamp"))
                for row in _extract_candidate_records(task, result):
                    candidate_records += 1
                    key = (row.task_id, _summary_record_group_key(row))
                    current = best_by_group.get(key)
                    if current is None or self._is_better_record(row, current):
                        best_by_group[key] = row

        existing_items = [
            item
            for task_id in task_ids
            for item in self._list_summary_indexes(task_id=task_id)
        ]
        for item in existing_items:
            if item.get("id") is not None:
                _summary_index_repository.delete(int(item["id"]))

        for row in best_by_group.values():
            _summary_index_repository.save(self._summary_index_payload(row, is_best=True))
        return {
            "processed": processed,
            "processed_tasks": len(task_ids),
            "candidate_records": candidate_records,
        }

    @staticmethod
    def _list_task_results(task_id: str) -> list[Any]:
        """按单个任务 ID 分页读取结果，避免跨任务全表查询。"""
        page_index = 1
        results: list[Any] = []
        while True:
            page = _task_result_repository.list_results(
                page_index=page_index,
                page_size=200,
                task_ids=[str(task_id)],
                order_field="timestamp",
                order_type="desc",
            )
            results.extend(page["items"])
            if not page["items"] or page_index * 200 >= page["total"]:
                return results
            page_index += 1

    def _is_better_record(self, candidate: SummaryRecord, current: SummaryRecord) -> bool:
        """按指标值、结果时间和结果 ID 比较两个汇总候选记录。"""
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

    def _summary_from_items(self, items) -> dict[str, int]:
        """统计结果列表中的股票、任务和不同超额收益阈值数量。"""
        stock_codes: set[str] = set()
        cn_stock_codes: set[str] = set()
        us_stock_codes: set[str] = set()
        task_ids: set[str] = set()
        return_beats_counts = {
            "return_beats_gt_0": 0,
            "return_beats_gt_20": 0,
            "return_beats_gt_50": 0,
            "return_beats_gt_100": 0,
        }

        for item in items:
            stock_code = str((item or {}).get("stock_code") or "").strip()
            if stock_code:
                stock_codes.add(stock_code)
                if _is_cn_stock_code(stock_code):
                    cn_stock_codes.add(stock_code)
                else:
                    us_stock_codes.add(stock_code)

            task_id = str((item or {}).get("task_id") or "").strip()
            if task_id:
                task_ids.add(task_id)

            value = _safe_number((item or {}).get("best_metric_value"))
            if value is None:
                continue
            if value > 0:
                return_beats_counts["return_beats_gt_0"] += 1
            if value > 0.2:
                return_beats_counts["return_beats_gt_20"] += 1
            if value > 0.5:
                return_beats_counts["return_beats_gt_50"] += 1
            if value > 1:
                return_beats_counts["return_beats_gt_100"] += 1

        return {
            "stock_count": len(stock_codes),
            "cn_stock_count": len(cn_stock_codes),
            "us_stock_count": len(us_stock_codes),
            "task_count": len(task_ids),
            **return_beats_counts,
        }

    def _count_index_rows(self, task_type: str | None = None, task_id: str | None = None) -> int:
        """按可选任务类型和任务 ID 统计远程汇总索引行数。"""
        return len(self._list_summary_indexes(task_id=task_id, task_type=task_type))

    def _dedupe_best_per_task(self, task_type: str | None = None, task_id: str | None = None) -> int:
        """在业务层按任务和周期选最佳远程索引，再逐条删除重复记录。"""
        records = self._list_summary_indexes(task_id=task_id, task_type=task_type)
        best_by_group: dict[tuple[str, str], dict[str, Any]] = {}
        duplicate_ids: list[int] = []
        for item in records:
            group_key = str(
                item.get("period_key")
                or item.get("year_label")
                or item.get("kline_range")
                or ""
            )
            key = (str(item.get("task_id") or ""), group_key)
            current = best_by_group.get(key)
            if current is None or self._is_better_index_item(item, current):
                if current and current.get("id") is not None:
                    duplicate_ids.append(int(current["id"]))
                best_by_group[key] = item
            elif item.get("id") is not None:
                duplicate_ids.append(int(item["id"]))
        for index_id in duplicate_ids:
            _summary_index_repository.delete(index_id)
        for item in best_by_group.values():
            if not item.get("is_best"):
                item["is_best"] = True
                _summary_index_repository.save(item)
        return len(duplicate_ids)

    def _keep_only_best_for_task(self, task_id: str) -> None:
        """对单个任务按周期保留最佳远程索引，并删除其余候选。"""
        self._dedupe_best_per_task(task_id=task_id)

    @staticmethod
    def _is_better_index_item(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
        """比较远程索引项，保持数据库窗口排序的时间、指标、ID 优先级。"""
        candidate_time = _parse_result_timestamp(candidate.get("result_timestamp")) or datetime.min
        current_time = _parse_result_timestamp(current.get("result_timestamp")) or datetime.min
        if candidate_time != current_time:
            return candidate_time > current_time
        candidate_value = _safe_number(candidate.get("best_metric_value"))
        current_value = _safe_number(current.get("best_metric_value"))
        if candidate_value != current_value:
            return (candidate_value if candidate_value is not None else float("-inf")) > (
                current_value if current_value is not None else float("-inf")
            )
        return int(candidate.get("id") or 0) > int(current.get("id") or 0)

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
        """更新后台重建任务状态、进度和可见日志消息。"""
        task = _task_repository.get(task_id)
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
            _task_log_repository.save({"task_id": task_id, "level": level, "message": message})
        _task_repository.save(task)

    def _job_with_task_status(self, job: dict[str, Any]) -> dict[str, Any]:
        """用持久化任务状态刷新进程内作业描述。"""
        task_id = job.get("task_id") or job.get("job_id")
        task = _task_repository.get(task_id) if task_id else None
        if task:
            job["task"] = task.to_dict()
            job["status"] = task.status
            if task.status == "completed":
                job["message"] = "索引重建完成"
            elif task.status == "error":
                job["message"] = task.error_message or "索引重建失败"
        return job

    def _job_from_task(self, task_id: str | None) -> dict[str, Any] | None:
        """将持久化的汇总重建任务转换为作业状态 DTO。"""
        if not task_id:
            return None
        task = _task_repository.get(task_id)
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
        """按任务类型选择普通模型或回测模型的摘要列定义。"""
        return BACKTEST_SUMMARY_COLUMNS if normalize_task_type(task_type) == "backtest_training" else SUMMARY_COLUMNS

    def _export_filename(self, filters: dict[str, Any], summary_type: str) -> str:
        """根据筛选条件或用户自定义名称生成安全的 CSV 文件名。"""
        custom_filename = self._safe_filename_part(filters.get("filename"))
        if custom_filename and custom_filename != "all":
            return custom_filename if custom_filename.lower().endswith(".csv") else f"{custom_filename}.csv"

        task_type = self._safe_filename_part(filters.get("task_type") or "all")
        stock_code = self._safe_filename_part(filters.get("stock_code") or "all")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"model_summary_{summary_type}_{task_type}_{stock_code}_{timestamp}.csv"

    def _safe_filename_part(self, value: Any) -> str:
        """移除文件名非法字符并限制片段长度。"""
        text = str(value or "").strip()
        if not text:
            return "all"
        text = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text)
        return text[:80] or "all"

    def _render_csv(self, columns: list[dict[str, str]], items: list[dict[str, Any]]) -> str:
        """按当前列定义把汇总记录渲染为 UTF-8 CSV 文本。"""
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        headers = (
            [label for _key, label in CSV_LEADING_COLUMNS]
            + ["参数"]
            + ["年份/区间"]
            + [column.get("label") or column.get("key") or "" for column in columns]
            + [label for _key, label in CSV_TRAILING_COLUMNS]
        )
        writer.writerow(headers)

        for item in items:
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            row = [
                self._csv_column_value(item, key, "percent" if key == "best_metric_value" else None)
                for key, _label in CSV_LEADING_COLUMNS
            ]
            row.append(_format_csv_parameter_summary(item.get("parameter_summary")))
            row.append(_interval_display_value(item))
            row.extend(
                _format_csv_metric(metrics.get(column.get("key")), column.get("format"))
                for column in columns
            )
            row.extend(
                self._csv_column_value(item, key)
                for key, _label in CSV_TRAILING_COLUMNS
            )
            writer.writerow(row)
        return buffer.getvalue()

    def _csv_column_value(
        self,
        item: dict[str, Any],
        key: str,
        format_name: str | None = None,
    ) -> str:
        """格式化单个 CSV 列，兼容任务类型、时间和指标格式。"""
        value = item.get(key)
        if key == "task_type":
            return TASK_TYPE_LABELS.get(str(value or ""), _csv_text(value))
        if key == "result_timestamp" and value:
            return str(value).replace("T", " ")
        if format_name:
            return _format_csv_metric(value, format_name)
        return _csv_text(value)

    def _empty_response(
        self,
        page: int,
        per_page: int,
        columns: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """返回与正常分页结构一致的空查询响应。"""
        return {
            "status": "success",
            "columns": columns or SUMMARY_COLUMNS,
            "summary": self._summary_from_items([]),
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
