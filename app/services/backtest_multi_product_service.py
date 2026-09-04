"""Multi-product backtest task service and preview helpers."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import current_app
from app.models import Task, TaskResult
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_result_return_repository import TaskResultReturnRepository
from app.repositories.backtest_product_result_cache_repository import BacktestProductResultCacheRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.sdk_client import SdkDuplicateKeyError
from app.services.backtest_training_service import BacktestTrainingService
from app.services.config_manager import get_config_manager
from app.services.task.error_handling import format_task_error_message, record_task_exception
from app.services.xpl_service import xpl_analyzer
from app.utils.db_retry import db_retry_manager, safe_db_operation
from app.utils.task_error_utils import unwrap_exception
from app.utils.return_series import build_return_series_fields, parse_return_series_fields
from app.utils.market import (
    infer_market_type,
    normalize_market_type as normalize_supported_market_type,
    normalize_stock_code,
)


BACKTEST_MULTI_PRODUCT_TASK_TYPE = "backtest_multi_product"
RATIO_BASE = Decimal("100")
GLOBAL_PREVIEW_CACHE_MAX_SIZE = 64
_GLOBAL_PREVIEW_CACHE: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
_task_result_repository = TaskResultRepository()
_task_result_return_repository = TaskResultReturnRepository()
_cache_repository = BacktestProductResultCacheRepository()
_task_repository = TaskRepository()

SUMMARY_ROW_DEFS = [
    ("绝对收益", "年化收益", "index_annualized_return", "start_annualized_return", "percent"),
    ("绝对收益", "盈利年份百分比", "index_profit_annual", "start_profit_annual", "percent"),
    ("绝对收益", "月盈利百分比", "index_profit_monthly_percentage", "start_profit_monthly_percentage", "percent"),
    ("绝对收益", "平均月收益率", "index_avg_monthly_return", "start_avg_monthly_return", "percent"),
    ("绝对收益", "月收益率波动率", "index_monthly_return_volatility", "start_monthly_return_volatility", "percent"),
    ("相对收益", "年化超额收益", None, "annualized_return_diff", "percent"),
    ("相对收益", "跑赢年份(百分比)", None, "outperform_year", "percent"),
    ("相对收益", "月超额收益胜率", None, "monthly_excess_return_percentage", "percent"),
    ("相对收益", "平均月超额", None, "avg_monthly_excess_return", "percent"),
    ("相对收益", "月超额波动率", None, "monthly_excess_volatility", "percent"),
    ("回撤", "年最大超额回撤", None, "year_max_excess_drawdown", "percent"),
    ("回撤", "超额回撤胜率", None, "excess_drawdown_winning_rate", "percent"),
    ("回撤", "年最大回撤", None, "start_max_drawdown", "percent"),
    ("回撤", "最大修复天数", None, "start_maximum_number_of_backtest_repair_days", "number"),
    ("回撤", "超额最大修复天数", None, "excess_maximum_number_of_backtest_repair_days", "number"),
    ("比率", "夏普比率", "index_sharpe_ratio", "start_sharpe_ratio", "number"),
    ("比率", "卡玛比率", "index_kama_ratio", "start_kama_ratio", "number"),
    ("比率", "所提诺比率", "index_sotino_ratio", "start_sotino_ratio", "number"),
    ("夏普", "超额夏普", None, "excess_sharp", "number"),
    ("所提诺", "超额所提诺比率", None, "excess_of_promissory_note", "number"),
]


def normalize_market_type(value: Any) -> str:
    return normalize_supported_market_type(value, "cn")


def normalize_price_mode(value: Any) -> str:
    """将价格模式归一为系统支持的标准枚举值。"""
    normalized = str(value or "").strip().lower()
    if normalized in {"kp_price", "sp_price", "vwap_price"}:
        return normalized
    return "vwap_price"


def parse_ratio(value: Any) -> Decimal:
    """解析比例输入，兼容小数与百分号文本。"""
    raw = str(value if value is not None else "").strip().replace("%", "")
    if not raw:
        raise ValueError("产品比例不能为空")
    try:
        ratio = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"产品比例不是有效数字: {value}") from exc
    if ratio < 0:
        raise ValueError("产品比例不能小于 0")
    return ratio


def normalize_ratio_display(value: Any) -> str:
    """将比例转换为稳定的前端展示文本。"""
    ratio = parse_ratio(value)
    normalized = ratio.quantize(Decimal("0.0001")).normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _hash_text(value: Any) -> str:
    """为缓存签名生成稳定的 UTF-8 SHA-1 摘要。"""
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _is_fixed_product(product: dict[str, Any]) -> bool:
    """判断产品是否标记为可复用结果的固定比例产品。"""
    return bool(product.get("is_fixed"))


def _global_preview_cache_key(
    task_id: str,
    products: list[dict[str, Any]],
    results: list[TaskResult],
) -> tuple[Any, ...]:
    """基于任务、比例和结果版本构造全局预览缓存键。"""
    ratio_signature = tuple(normalize_ratio_display(product.get("ratio")) for product in products)
    result_signature = tuple(
        (
            result.id,
            result.step_index,
            bool(result.success),
            result.return_series_id,
            result.timestamp.isoformat() if result.timestamp else None,
            _hash_text(result.parameters or ""),
            _hash_text(result.result or ""),
        )
        for result in results
    )
    return (task_id, ratio_signature, result_signature)


def _get_global_preview_cache(cache_key: tuple[Any, ...]) -> dict[str, Any] | None:
    """读取全局预览 LRU 缓存，并将命中项标记为最近使用。"""
    cached = _GLOBAL_PREVIEW_CACHE.get(cache_key)
    if cached is None:
        return None
    _GLOBAL_PREVIEW_CACHE.move_to_end(cache_key)
    return deepcopy(cached)


def _set_global_preview_cache(cache_key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    """保存多品全局预览缓存并淘汰超过容量限制的最旧项。"""
    _GLOBAL_PREVIEW_CACHE[cache_key] = deepcopy(payload)
    _GLOBAL_PREVIEW_CACHE.move_to_end(cache_key)
    while len(_GLOBAL_PREVIEW_CACHE) > GLOBAL_PREVIEW_CACHE_MAX_SIZE:
        _GLOBAL_PREVIEW_CACHE.popitem(last=False)


def _normalize_sheet(product: dict[str, Any]) -> dict[str, str]:
    """规范化产品内嵌 Sheet 配置，确保名称和 ID 字段一致。"""
    sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
    spreadsheet_id = str(sheet.get("spreadsheet_id") or product.get("spreadsheet_id") or "").strip()
    sheet_name = str(sheet.get("sheet_name") or product.get("sheet_name") or "data").strip()
    title = str(sheet.get("title") or product.get("title") or "").strip()
    if not spreadsheet_id:
        raise ValueError("每个产品都必须配置 Google Sheet 链接")
    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name or "data",
        "title": title,
    }


def normalize_multi_product_config(config: dict[str, Any]) -> dict[str, Any]:
    """规范化多品回测配置，补齐产品和市场的兼容字段。"""
    if not isinstance(config, dict):
        raise ValueError("多品数据回测 config 必须是 JSON 对象")

    start_date = str(config.get("start_date") or "").strip()
    end_date = str(config.get("end_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date):
        raise ValueError("请填写有效的 K 线开始日期")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_date):
        raise ValueError("请填写有效的 K 线结束日期")
    if start_date > end_date:
        raise ValueError("K 线开始日期不能晚于结束日期")

    products = config.get("products")
    if not isinstance(products, list) or len(products) < 2:
        raise ValueError("多品数据回测至少需要 2 个产品")

    normalized_products = []
    expected_parameter_count = None
    for index, product in enumerate(products, start=1):
        if not isinstance(product, dict):
            raise ValueError(f"产品 {index} 配置格式不正确")
        raw_stock_code = str(product.get("stock_code") or "").strip().upper()
        market_type = normalize_market_type(
            product.get("market_type") or config.get("market_type")
        ) or infer_market_type(raw_stock_code)
        stock_code = normalize_stock_code(
            raw_stock_code,
            market_type,
            product.get("exchange_market") or config.get("exchange_market"),
        )
        if not stock_code:
            raise ValueError(f"产品 {index} 缺少股票代码")
        parameters = product.get("parameters")
        if not isinstance(parameters, list) or not parameters:
            raise ValueError(f"产品 {index} 至少需要一行参数")
        for row_index, row in enumerate(parameters, start=1):
            if not isinstance(row, list) or not any(str(item).strip() for item in row):
                raise ValueError(f"产品 {index} 第 {row_index} 行参数为空")
        if expected_parameter_count is None:
            expected_parameter_count = len(parameters)
        elif len(parameters) != expected_parameter_count:
            raise ValueError("所有产品的参数行数必须一致，才能按行号对齐")

        normalized_products.append({
            **product,
            "product_index": index - 1,
            "product_name": str(product.get("product_name") or product.get("name") or stock_code).strip(),
            "stock_code": stock_code,
            "market_type": market_type,
            "price_mode": normalize_price_mode(product.get("price_mode") or config.get("price_mode")),
            "kline_adjustment": product.get("kline_adjustment") or config.get("kline_adjustment") or "forward",
            "kline_data_source": product.get("kline_data_source") or config.get("kline_data_source") or "dfcf",
            "ratio": normalize_ratio_display(product.get("ratio")),
            "is_fixed": bool(product.get("is_fixed")),
            "sheet": _normalize_sheet(product),
            "parameters": parameters,
        })

    return {
        **config,
        "start_date": start_date,
        "end_date": end_date,
        "products": normalized_products,
    }


def _parse_json(raw: Any, default: Any) -> Any:
    """安全解析远程字段中的 JSON 文本，失败时回退默认值。"""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _sort_task_results(results: list[TaskResult]) -> list[TaskResult]:
    """补足 SDK 单字段排序限制，按旧预览顺序在内存中稳定排序。"""
    return sorted(
        results,
        key=lambda result: (
            int(result.step_index) if result.step_index is not None else -1,
            str(result.timestamp or ""),
            int(result.id),
        ),
    )


def _all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    """从年度记录中读取 all 聚合项或第一个可用项。"""
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def _extract_result_core(task_result: TaskResult) -> dict[str, Any]:
    """从任务结果对象中提取核心结果载荷。"""
    payload = _parse_json(task_result.result, {})
    if not isinstance(payload, dict) or not payload:
        return {}

    prioritized_keys = (
        "calculate_metrics",
        "weighted_calculate_metrics",
        "analyze_result",
    )
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        if any(key in value for key in prioritized_keys):
            return value

    first_value = next(iter(payload.values()), {})
    return first_value if isinstance(first_value, dict) else {}


def _extract_return_date_from_result_payload(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从结果载荷解析按日期排列的收益明细。"""
    if not isinstance(result_payload, dict):
        return []
    direct_return_date = result_payload.get("_return_date")
    if isinstance(direct_return_date, list):
        return direct_return_date
    value = list(result_payload.values())[0] if result_payload else {}
    if not isinstance(value, dict):
        return []
    return_date = value.get("return_date")
    return return_date if isinstance(return_date, list) else []


def _safe_number(value: Any) -> float | None:
    """将输入安全转换为有限浮点数，无法转换时返回空值。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    raw = str(value).strip().replace(",", "").replace("$", "")
    if not raw or raw == "-":
        return None
    try:
        if raw.endswith("%"):
            return float(raw[:-1]) / 100
        return float(raw)
    except ValueError:
        return None


def _year_key(value: Any) -> str:
    """将年度字段转换为可用于跨来源匹配的规范字符串。"""
    text = str(value if value is not None else "").strip()
    if not text or text.lower() == "all":
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _derive_year_max_excess_drawdown(calculate_metrics: dict[str, Any]) -> float | None:
    """计算跑赢年份中策略相对指数的最大年度回撤差。"""
    annual_excess_returns = [
        (year, _safe_number(item.get("annualized_return_diff")))
        for item in calculate_metrics.get("excess_returns") or []
        if isinstance(item, dict)
        for year in [_year_key(item.get("year"))]
        if year
    ]
    if not annual_excess_returns:
        return None

    excess_years = {
        year
        for year, annualized_return_diff in annual_excess_returns
        if annualized_return_diff is not None and annualized_return_diff > 0
    }
    if not excess_years:
        return 0.0

    index_max_dd = calculate_metrics.get("index_maximum_drawdown") or {}
    start_max_dd = calculate_metrics.get("start_maximum_drawdown") or {}
    index_year_map = {
        year: item
        for item in index_max_dd.get("year_maximum_drawdown", [])
        if isinstance(item, dict)
        for year in [_year_key(item.get("year"))]
        if year in excess_years
    }
    start_year_map = {
        year: item
        for item in start_max_dd.get("year_maximum_drawdown", [])
        if isinstance(item, dict)
        for year in [_year_key(item.get("year"))]
        if year in excess_years
    }

    diffs = []
    for year, index_item in index_year_map.items():
        start_item = start_year_map.get(year) or {}
        index_drawdown = _safe_number(index_item.get("drawdown"))
        start_drawdown = _safe_number(start_item.get("drawdown"))
        if index_drawdown is None or start_drawdown is None:
            continue
        diffs.append(index_drawdown - start_drawdown)
    return max(diffs) if diffs else None


def _negative_number(value: Any) -> float | None:
    """将有效数值转换为非正展示值，空值保持为空。"""
    number = _safe_number(value)
    if number is None:
        return None
    if number == 0:
        return 0.0
    return -abs(number)


def _fmt_value(value: Any, value_type: str) -> str:
    """按百分比或普通数值格式输出摘要表中的展示文本。"""
    number = _safe_number(value)
    if number is None:
        return "" if value in (None, "") else str(value)
    if value_type == "percent":
        return f"{number:.2%}"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _scale_return_date(
    return_date: list[dict[str, Any]],
    ratio: Any,
) -> list[dict[str, Any]]:
    """按产品比例缩放收益序列，供组合加权汇总使用。"""
    ratio_value = float(parse_ratio(ratio) / RATIO_BASE)
    scaled = []
    for item in return_date:
        date = item.get("date") or item.get("stock_date")
        index_return = _safe_number(item.get("index_return"))
        start_return = _safe_number(item.get("start_return"))
        if not date or index_return is None or start_return is None:
            continue
        scaled.append({
            "date": date,
            "index_return": index_return * ratio_value,
            "start_return": start_return * ratio_value,
        })
    return scaled


def _build_returns_json(return_date: list[dict[str, Any]]) -> str:
    """将逐日收益记录编码为远端收益序列表使用的列式 JSON。"""
    dates = []
    index_returns = []
    start_returns = []
    for item in return_date:
        if not isinstance(item, dict):
            continue
        dates.append(item.get("date") or item.get("stock_date"))
        index_returns.append(item.get("index_return"))
        start_returns.append(item.get("start_return"))
    return json.dumps({
        "dates": dates,
        "index_returns": index_returns,
        "start_returns": start_returns,
    }, ensure_ascii=False, allow_nan=False)


def _parse_returns_json(raw: Any) -> list[dict[str, Any]]:
    """将列式收益 JSON 还原为逐日字典列表。"""
    payload = _parse_json(raw, {})
    if not isinstance(payload, dict):
        return []
    dates = payload.get("dates") or []
    index_returns = payload.get("index_returns") or []
    start_returns = payload.get("start_returns") or []
    return [
        {
            "date": date,
            "index_return": index_returns[index] if index < len(index_returns) else None,
            "start_return": start_returns[index] if index < len(start_returns) else None,
        }
        for index, date in enumerate(dates)
    ]


def _get_return_date_for_task_result(task_result: TaskResult) -> list[dict[str, Any]]:
    """优先读取关联收益序列，不存在时兼容旧结果载荷内的收益数据。"""
    if task_result.return_series_id:
        return_series = _task_result_return_repository.get(task_result.return_series_id)
        if return_series:
            return parse_return_series_fields(return_series)
    return _extract_return_date_from_result_payload(_parse_json(task_result.result, {}))


def _set_weighted_metrics_on_result_payload(
    result_payload: dict[str, Any],
    weighted_calculate_metrics: dict[str, Any],
) -> dict[str, Any]:
    """将加权计算指标写入结果载荷的首个模型结果对象。"""
    if not isinstance(result_payload, dict) or not result_payload:
        return result_payload
    first_key = next(iter(result_payload))
    value = result_payload.get(first_key)
    if isinstance(value, dict):
        value["weighted_calculate_metrics"] = weighted_calculate_metrics
    return result_payload


def _return_date_by_date(return_date: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """按日期索引有效收益行，便于多产品取共同交易日。"""
    rows: dict[str, dict[str, float]] = {}
    for item in return_date:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("stock_date") or "").strip()
        index_return = _safe_number(item.get("index_return"))
        start_return = _safe_number(item.get("start_return"))
        if not date or index_return is None or start_return is None:
            continue
        rows[date] = {
            "index_return": index_return,
            "start_return": start_return,
        }
    return rows


def _build_portfolio_return_date(
    product_results: dict[int, dict[str, Any]],
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """取各产品共同日期并按比例合成组合收益序列。"""
    product_return_maps: list[tuple[dict[str, dict[str, float]], Decimal]] = []
    common_dates: set[str] | None = None

    for product in products:
        product_index = int(product["product_index"])
        product_result = product_results.get(product_index) or {}
        return_map = _return_date_by_date(product_result.get("return_date") or [])
        if not return_map:
            return []
        common_dates = set(return_map) if common_dates is None else common_dates & set(return_map)
        product_return_maps.append((return_map, parse_ratio(product.get("ratio")) / RATIO_BASE))

    if not common_dates:
        return []

    return_date = []
    for date in sorted(common_dates):
        index_total = Decimal("0")
        start_total = Decimal("0")
        for return_map, ratio in product_return_maps:
            row = return_map[date]
            index_total += Decimal(str(row["index_return"])) * ratio
            start_total += Decimal(str(row["start_return"])) * ratio
        return_date.append({
            "date": date,
            "index_return": float(index_total),
            "start_return": float(start_total),
        })
    return return_date


def _build_portfolio_metrics(
    product_results: dict[int, dict[str, Any]],
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    """从组合加权收益序列计算组合层面的回测指标。"""
    return_date = _build_portfolio_return_date(product_results, products)
    if not return_date:
        return {}
    calculate_metrics = xpl_analyzer.get_calculate_metrics_v1(return_date)
    return calculate_metrics if isinstance(calculate_metrics, dict) else {}


def _build_weighted_product_metrics(
    return_date: list[dict[str, Any]],
    ratio: Any,
) -> dict[str, Any]:
    """按单个产品比例缩放收益序列后计算其加权指标。"""
    scaled = _scale_return_date(return_date, ratio)
    if not scaled:
        return {}
    calculate_metrics = xpl_analyzer.get_calculate_metrics_v1(scaled)
    return calculate_metrics if isinstance(calculate_metrics, dict) else {}


def _derive_metrics(calculate_metrics: dict[str, Any]) -> dict[str, Any]:
    """从原始计算指标中提取汇总表统一使用的扁平字段。"""
    def _metric_value(*keys: str) -> Any:
        """按优先顺序读取第一个非空的同义指标字段。"""
        for key in keys:
            value = calculate_metrics.get(key)
            if value not in (None, ""):
                return value
        return None

    def _first_value(*values: Any) -> Any:
        """从多个候选值中返回首个有效值。"""
        for value in values:
            if value not in (None, ""):
                return value
        return None

    excess_all = _all_entry(calculate_metrics.get("excess_returns"))
    index_profit_monthly_all = _all_entry(calculate_metrics.get("index_profit_monthly"))
    start_profit_monthly_all = _all_entry(calculate_metrics.get("start_profit_monthly"))
    monthly_excess_percentage_all = _all_entry(
        calculate_metrics.get("monthly_excess_return_percentage")
    )
    index_kama_all = _all_entry(calculate_metrics.get("index_kama_ratio"))
    start_kama_all = _all_entry(calculate_metrics.get("start_kama_ratio"))
    index_sotino_all = _all_entry(calculate_metrics.get("index_sotino_ratio"))
    start_sotino_all = _all_entry(calculate_metrics.get("start_sotino_ratio"))
    index_sharpe_all = (calculate_metrics.get("index_sharpe_ratios") or {}).get("all") or {}
    start_sharpe_all = (calculate_metrics.get("start_sharpe_ratios") or {}).get("all") or {}
    monthly_excess_returns = calculate_metrics.get("monthly_excess_returns") or []
    monthly_excess_values = [
        item.get("monthly_excess_return_diff")
        for item in monthly_excess_returns
        if isinstance(item, dict) and item.get("monthly_excess_return_diff") is not None
    ]
    avg_monthly_excess_return = (
        sum(monthly_excess_values) / len(monthly_excess_values)
        if monthly_excess_values
        else None
    )
    total_max_drawdown = (
        (calculate_metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown")
        or {}
    )
    year_max_excess_drawdown = _derive_year_max_excess_drawdown(calculate_metrics)
    return {
        "index_annualized_return": _first_value(excess_all.get("index_annualized_return"), _metric_value("index_annualized_return")),
        "start_annualized_return": _first_value(excess_all.get("start_annualized_return"), _metric_value("start_annualized_return")),
        "annualized_return_diff": _first_value(excess_all.get("annualized_return_diff"), _metric_value("annualized_return_diff")),
        "index_profit_annual": calculate_metrics.get("index_profit_annual"),
        "start_profit_annual": calculate_metrics.get("start_profit_annual"),
        "index_profit_monthly_percentage": _first_value(index_profit_monthly_all.get("profit_monthly_percentage"), _metric_value("index_profit_monthly_percentage")),
        "start_profit_monthly_percentage": _first_value(start_profit_monthly_all.get("profit_monthly_percentage"), _metric_value("start_profit_monthly_percentage")),
        "index_avg_monthly_return": _first_value(index_sharpe_all.get("avg_monthly_return"), _metric_value("index_avg_monthly_return_common", "index_avg_monthly_return")),
        "start_avg_monthly_return": _first_value(start_sharpe_all.get("avg_monthly_return"), _metric_value("start_avg_monthly_return_common", "start_avg_monthly_return")),
        "index_monthly_return_volatility": calculate_metrics.get("index_monthly_return_volatility"),
        "start_monthly_return_volatility": calculate_metrics.get("start_monthly_return_volatility"),
        "outperform_year": calculate_metrics.get("outperform_year"),
        "monthly_excess_return_percentage": _first_value(monthly_excess_percentage_all.get("excess_return"), _metric_value("monthly_excess_return_percentage", "monthly_excess_return_percentage_last_return")),
        "avg_monthly_excess_return": _first_value(avg_monthly_excess_return, _metric_value("avg_monthly_excess_returns", "avg_monthly_excess_return")),
        "monthly_excess_volatility": calculate_metrics.get("monthly_excess_volatility"),
        "year_max_excess_drawdown": year_max_excess_drawdown if year_max_excess_drawdown is not None else _metric_value("max_drawdown", "year_max_excess_drawdown"),
        "excess_drawdown_winning_rate": _safe_number(calculate_metrics.get("excess_drawdown_winning_rate")),
        "start_max_drawdown": _negative_number(_first_value(total_max_drawdown.get("drawdown"), _metric_value("start_drawdown", "start_max_drawdown"))),
        "start_maximum_number_of_backtest_repair_days": calculate_metrics.get("start_maximum_number_of_backtest_repair_days"),
        "excess_maximum_number_of_backtest_repair_days": calculate_metrics.get("excess_maximum_number_of_backtest_repair_days"),
        "index_sharpe_ratio": _first_value(index_sharpe_all.get("sharpe_ratio"), _metric_value("index_sharpe_ratio")),
        "start_sharpe_ratio": _first_value(start_sharpe_all.get("sharpe_ratio"), _metric_value("start_sharpe_ratio")),
        "index_kama_ratio": _first_value(index_kama_all.get("kama_ratio"), _metric_value("index_kama_ratio")),
        "start_kama_ratio": _first_value(start_kama_all.get("kama_ratio"), _metric_value("start_kama_ratio")),
        "index_sotino_ratio": _first_value(index_sotino_all.get("sotino_ratio"), _metric_value("index_sotino_ratio")),
        "start_sotino_ratio": _first_value(start_sotino_all.get("sotino_ratio"), _metric_value("start_sotino_ratio")),
        "excess_sharp": calculate_metrics.get("excess_sharp"),
        "excess_of_promissory_note": calculate_metrics.get("excess_of_promissory_note"),
    }


class BacktestMultiProductService(BacktestTrainingService):
    """Multi-product backtest service with independent product sheets."""

    @staticmethod
    def _build_fixed_product_cache_key(
        config_data: dict[str, Any],
        product: dict[str, Any],
        parameter: list[Any],
    ) -> str:
        """基于产品、区间、行情来源和参数组合生成固定产品缓存键。"""
        sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
        payload = {
            "stock_code": str(product.get("stock_code") or "").strip().upper(),
            "market_type": normalize_market_type(product.get("market_type")),
            "start_date": str(config_data.get("start_date") or "").strip(),
            "end_date": str(config_data.get("end_date") or "").strip(),
            "price_mode": normalize_price_mode(product.get("price_mode") or config_data.get("price_mode")),
            "kline_adjustment": product.get("kline_adjustment") or config_data.get("kline_adjustment") or "forward",
            "spreadsheet_id": str(sheet.get("spreadsheet_id") or product.get("spreadsheet_id") or "").strip(),
            "sheet_name": str(sheet.get("sheet_name") or product.get("sheet_name") or "data").strip() or "data",
            "sheet_title": str(sheet.get("title") or product.get("title") or "").strip(),
            "parameter": parameter,
        }
        return _hash_text(payload)

    @classmethod
    def fixed_product_cache_exists(
        cls,
        config_data: dict[str, Any],
        product: dict[str, Any],
    ) -> bool:
        """判断固定比例产品是否已有可复用的远程回测缓存。"""
        batch_id = str(config_data.get("fixed_product_batch_id") or "").strip()
        if not batch_id or not _is_fixed_product(product):
            return False
        parameters = product.get("parameters") if isinstance(product.get("parameters"), list) else []
        if not parameters:
            return False
        for parameter in parameters:
            cache_key = cls._build_fixed_product_cache_key(config_data, product, parameter)
            exists = _cache_repository.find_by_business_key(batch_id, cache_key)
            if not exists:
                return False
        return True

    def _get_fixed_product_cache(
        self,
        config_data: dict[str, Any],
        product: dict[str, Any],
        parameter: list[Any],
    ) -> dict[str, Any] | None:
        """按业务键读取固定产品缓存。"""
        batch_id = str(config_data.get("fixed_product_batch_id") or "").strip()
        if not batch_id or not _is_fixed_product(product):
            return None
        cache_key = self._build_fixed_product_cache_key(config_data, product, parameter)
        cache_entry = _cache_repository.find_by_business_key(batch_id, cache_key)
        if not cache_entry:
            return None
        return {
            "result_json": cache_entry.get("result_json"),
            "returns_json": cache_entry.get("returns_json"),
            "source_task_id": cache_entry.get("source_task_id"),
            "source_step_index": cache_entry.get("source_step_index"),
        }

    def _save_fixed_product_cache(
        self,
        config_data: dict[str, Any],
        product: dict[str, Any],
        parameter: list[Any],
        result_payload: dict[str, Any],
        return_date: list[dict[str, Any]] | None,
        step_index: int,
    ) -> None:
        """尝试写入固定产品缓存；唯一冲突时保留先成功的内容。"""
        batch_id = str(config_data.get("fixed_product_batch_id") or "").strip()
        if not batch_id or not _is_fixed_product(product):
            return

        cache_key = self._build_fixed_product_cache_key(config_data, product, parameter)
        try:
            _cache_repository.save({
                "batch_id": batch_id,
                "cache_key": cache_key,
                "result_json": self._sanitize_json_value(result_payload),
                "returns_json": _build_returns_json(return_date or []) if return_date else None,
                "source_task_id": self.task_id,
                "source_step_index": step_index,
            })
        except SdkDuplicateKeyError:
            # 唯一约束冲突表示其他执行者已成功写入，不能覆盖其内容。
            return

    def _build_cached_result_parameters(
        self,
        config_data: dict[str, Any],
        product: dict[str, Any],
        group_index: int,
        parameter: list[Any],
        return_date: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """根据缓存收益序列重建写入任务结果所需的参数元数据。"""
        dates = [
            str(item.get("date") or item.get("stock_date") or "").strip()
            for item in return_date
            if isinstance(item, dict) and (item.get("date") or item.get("stock_date"))
        ]
        return {
            "parameter": parameter,
            "stock_code": product["stock_code"],
            "year": f"{config_data['start_date']}~{config_data['end_date']}",
            "Kline_key": f"{config_data['start_date']}~{config_data['end_date']}",
            "product_index": int(product["product_index"]),
            "product_name": product["product_name"],
            "ratio": product["ratio"],
            "parameter_group_index": group_index,
            "kline": [dates[0], dates[-1]] if dates else [],
            "start_date": config_data["start_date"],
            "end_date": config_data["end_date"],
            "sheet": product["sheet"],
            "is_fixed": True,
            "fixed_product_batch_id": config_data.get("fixed_product_batch_id"),
        }

    def _save_result_from_fixed_product_cache(
        self,
        step_index: int,
        config_data: dict[str, Any],
        product: dict[str, Any],
        group_index: int,
        parameter: list[Any],
        cache_entry: dict[str, Any],
    ) -> None:
        """将命中的固定产品缓存转换为当前任务的一条成功结果。"""
        result_payload = _parse_json(cache_entry.get("result_json"), {})
        return_date = _parse_returns_json(cache_entry.get("returns_json"))
        parameters = self._build_cached_result_parameters(
            config_data,
            product,
            group_index,
            parameter,
            return_date,
        )
        self._save_task_result(
            step_index,
            parameters,
            result_payload if isinstance(result_payload, dict) else {},
            True,
            return_date=return_date,
        )

    @staticmethod
    def _build_kline_signature(kline: list[dict[str, Any]]) -> dict[str, Any]:
        """提取首、中、末行情行形成轻量签名，识别 Sheet 输入是否可复用。"""
        if not kline:
            return {}
        middle_index = len(kline) // 2
        return {
            "length": len(kline),
            "first": kline[0],
            "middle": kline[middle_index],
            "last": kline[-1],
        }

    @staticmethod
    def _build_sheet_cache_key(product: dict[str, Any]) -> str:
        """以表格 ID 和工作表名生成单次执行内的输入缓存键。"""
        sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
        spreadsheet_id = str(sheet.get("spreadsheet_id") or "").strip()
        sheet_name = str(sheet.get("sheet_name") or "").strip()
        return f"{spreadsheet_id}::{sheet_name}"

    def _task_detail_url(self) -> str:
        """构造多品回测任务详情地址，供执行通知跳转。"""
        return f"{current_app.config.get('BASE_URL')}/backtest-multi-product/detail/{self.task_id}"

    def execute_task(self):
        """执行多品回测任务，并在每个产品完成后持久化结果。"""
        try:
            context_app = self.app or current_app
            with context_app.app_context():
                task = self._get_remote_task()
                self.task = task
                if not task:
                    self._log_error(f"任务 {self.task_id} 不存在")
                    return "error"
                if task.status == "cancelled" or self._is_cancel_requested():
                    self._log_info(f"任务 {self.task_id} 已被取消，停止执行")
                    return "cancelled"

                raw_config = _parse_json(task.config, {})
                config_data = {
                    **get_config_manager().get_google_sheet_config(),
                    **normalize_multi_product_config(raw_config),
                }
                self.task_name = task.name
                result = self._execute_products(task, config_data)
                if result == "completed":
                    self.task_ok_to_dd("多品数据回测任务执行完成")
                return result
        except Exception as exc:
            root = unwrap_exception(exc) or exc
            try:
                record = record_task_exception(self.task_id, exc, "execute_task", self.app)
                error_summary = format_task_error_message(record)
            except Exception as record_error:
                self._log_warning(f"记录任务异常失败: {record_error}")
                error_summary = f"{root.__class__.__name__}: {root}"
            self._log_error(f"执行多品数据回测任务失败: {self.task_id}, 错误: {root}")
            self._log_error(f"任务异常摘要: {error_summary}")
            return "error"

    def _execute_products(self, task: Task, config_data: dict[str, Any]) -> str:
        """按参数组和产品顺序执行回测，处理断点、缓存和持久化。"""
        products = config_data["products"]
        parameter_count = len(products[0]["parameters"])
        total_steps = parameter_count * len(products)
        self._save_remote_task(task, total_steps=total_steps)
        self._log_info(f"将执行 {parameter_count} 个参数方案、{len(products)} 个产品，共 {total_steps} 步")

        start_index = self._resolve_resume_start_index(task)
        sheet_kline_cache: dict[str, dict[str, Any]] = {}
        kline_cache: dict[int, dict[str, Any]] = {}
        success_count = start_index
        failed_count = 0
        processed_index = 0
        column_A_length = 0
        for product in products:
            for group_index in range(parameter_count):
                if self._is_cancel_requested():
                    return "cancelled"
                if processed_index < start_index:
                    processed_index += 1
                    continue

                result = self._get_remote_task()
                if not result or result.status == "cancelled":
                    self._log_warning("任务已被取消，停止执行")
                    return "cancelled"

                current_step = processed_index + 1
                product_index = int(product["product_index"])
                sheet_cache_key = self._build_sheet_cache_key(product)
                parameter = product["parameters"][group_index]
                product_config = self._build_product_config(config_data, product)
                cached_fixed_result = self._get_fixed_product_cache(config_data, product, parameter)
                if cached_fixed_result:
                    self._update_task_progress(current_step)
                    self._log_info(
                        f"固定产品结果命中同批缓存: 产品 {product['product_name']} / 方案 {group_index + 1}"
                    )
                    self._save_result_from_fixed_product_cache(
                        current_step - 1,
                        config_data,
                        product,
                        group_index,
                        parameter,
                        cached_fixed_result,
                    )
                    success_count += 1
                    processed_index += 1
                    self._log_info(f"第 {current_step} 步执行成功（缓存复用）")
                    continue
                self._init_google_sheet(product_config)
                kline_info = kline_cache.get(product_index)
                if not kline_info:
                    kline_info = self._build_product_kline(product, config_data)
                    kline_cache[product_index] = kline_info
                sheet_cache = sheet_kline_cache.setdefault(sheet_cache_key, {"combination": {}})
                cached_combination = sheet_cache.get("combination") or {}
                if cached_combination.get("product_index") != product_index:
                    sheet_cache["combination"] = {}

                input_column_d, input_column_v, output_range_1, output_range_2, output_column_index, output_column_start, parameter_positions, check_positions, last_row = self._c3_to_c5_get_config(
                    product_config)
                if hasattr(self, "google_sheet"):
                    A_num = self.google_sheet.get_last_row('A')
                    self._log_info(f'{self.google_sheet.title} 当前A列行数: {A_num}, 准备滞空 A列 B列')
                    self.google_sheet.clear_range(f"{input_column_d}2:{input_column_v}{A_num+2}")

                combination = {
                    "parameter": parameter,
                    "stock_code": product["stock_code"],
                    "year": kline_info["kline_key"],
                    "Kline_key": kline_info["kline_key"],
                    "kline_signature": kline_info["kline_signature"],
                    "product_index": product_index,
                    "product_name": product["product_name"],
                    "ratio": product["ratio"],
                    "parameter_group_index": group_index,
                }
                self._log_step(
                    current_step,
                    total_steps,
                    f"执行方案 {group_index + 1} / 产品 {product['product_name']}",
                )
                self._update_task_progress(current_step)

                try:
                    success, result_payload, return_date = self._execute_parameter_combination(
                        column_A_length,
                        combination,
                        sheet_cache,
                        product_config,
                        {kline_info["kline_key"]: kline_info["kline"]},
                    )
                    if not success:
                        failed_count += 1
                        self._log_warning(f"第 {current_step} 步执行失败")
                        return "error"

                    kline = kline_info["kline"]
                    column_A_length = len(kline)

                    self._save_task_result(current_step - 1, {
                        **combination,
                        "kline": [kline[0], kline[-1]],
                        "start_date": config_data["start_date"],
                        "end_date": config_data["end_date"],
                        "sheet": product["sheet"],
                        "is_fixed": _is_fixed_product(product),
                        "fixed_product_batch_id": config_data.get("fixed_product_batch_id"),
                    }, result_payload, True, return_date=return_date)
                    self._save_fixed_product_cache(
                        config_data,
                        product,
                        parameter,
                        result_payload,
                        return_date,
                        current_step - 1,
                    )
                    sheet_kline_cache[sheet_cache_key]["combination"] = combination
                    success_count += 1
                    self._log_info(f"第 {current_step} 步执行成功")
                except Exception as exc:
                    self._raise_retryable_network_error(exc, f"第 {current_step} 步网络请求失败")
                    failed_count += 1
                    record = record_task_exception(
                        self.task_id,
                        exc,
                        "execute_product_step",
                        self.app,
                    )
                    self._log_error(
                        f"第 {current_step} 步执行出错: {format_task_error_message(record)}"
                    )
                    return "error"
                processed_index += 1

        self._log_info(f"多品数据回测完成，总成功: {success_count}, 总失败: {failed_count}")
        return "completed" if success_count else "error"

    def _update_task_progress(self, current_step: int) -> None:
        """读取最新远端任务并更新其当前执行步骤。"""
        task = self._get_remote_task()
        if not task:
            return
        self._save_remote_task(task, current_step=current_step)

    def _save_task_result(
        self,
        step_index: int,
        parameters,
        result: dict[str, Any],
        success: bool,
        *,
        return_date: list[dict[str, Any]] | None = None,
    ):
        """保存单个产品结果及收益序列，并写入按比例计算的加权指标。"""
        def save_result_operation():
            safe_parameters = self._normalize_result_parameters(parameters)
            safe_result_payload = dict(result) if isinstance(result, dict) else {}
            weighted_calculate_metrics = _build_weighted_product_metrics(return_date or [], safe_parameters.get("ratio"))
            safe_result_payload = _set_weighted_metrics_on_result_payload(
                safe_result_payload,
                weighted_calculate_metrics,
            )
            safe_result = self._sanitize_json_value(
                self._prepare_result_for_persistence(safe_result_payload)
            )
            task_result = _task_result_repository.save({
                "task_id": self.task_id,
                "step_index": step_index,
                "parameters": safe_parameters,
                "result": safe_result,
                "success": success,
            })
            if return_date:
                series_fields = build_return_series_fields(
                    return_date,
                    stock_code=safe_parameters.get("stock_code"),
                    stock_name=(
                        safe_parameters.get("stock_name")
                        or safe_parameters.get("product_name")
                        or safe_parameters.get("stock_code")
                    ),
                    market_type=self._get_return_series_market_type(safe_parameters),
                    exchange_market=self._get_return_series_exchange_market(safe_parameters),
                )
                if not series_fields:
                    raise ValueError("收益序列缺少有效日期")
                return_series = _task_result_return_repository.save({
                    "task_id": self.task_id,
                    **series_fields,
                })
                _task_result_repository.save({
                    **task_result,
                    "return_series_id": return_series["id"],
                })

        try:
            context_app = self.app or current_app
            with context_app.app_context():
                safe_db_operation(save_result_operation)
        except Exception as exc:
            self._log_error(f"保存多品任务结果失败: {exc}")
            raise

    def _build_product_config(self, config_data: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
        """将全局配置与产品专属 Sheet、股票和行情配置合并。"""
        product_config = dict(config_data)
        product_config.update({
            "sheet": product["sheet"],
            "spreadsheet_id": product["sheet"]["spreadsheet_id"],
            "sheet_name": product["sheet"]["sheet_name"],
            "title": product["sheet"].get("title") or "",
            "stock_code": product["stock_code"],
            "market_type": product["market_type"],
            "kline_adjustment": product.get("kline_adjustment", "forward"),
        })
        return product_config

    def _build_product_kline(self, product: dict[str, Any], config_data: dict[str, Any]) -> dict[str, Any]:
        """加载产品日期区间 K 线，并构造供重复写入判断使用的签名。"""
        kline = self._get_kline_by_date_range(
            product["stock_code"],
            product["market_type"],
            config_data["start_date"],
            config_data["end_date"],
            price_mode=product.get("price_mode") or config_data.get("price_mode", "vwap_price"),
            adjust_type=product.get("kline_adjustment", "forward"),
            data_source=product.get("kline_data_source") or config_data.get("kline_data_source", "dfcf"),
            exchange_market=product.get("exchange_market"),
        )
        kline_key = f"{config_data['start_date']}~{config_data['end_date']}"
        return {
            "kline_key": kline_key,
            "kline": kline,
            "kline_signature": self._build_kline_signature(kline),
        }

    def _is_same_kline_source(self, combination: dict[str, Any], cached_combination: dict[str, Any]) -> bool:
        """判断当前参数组合能否复用上次已写入 Sheet 的行情数据。"""
        if combination.get("Kline_key") != cached_combination.get("Kline_key"):
            return False
        if combination.get("stock_code") != cached_combination.get("stock_code"):
            return False
        if combination.get("kline_signature") != cached_combination.get("kline_signature"):
            return False
        return True

    def _execute_parameter_combination(
        self,
        column_A_length,
        combination,
        cache_parameters,
        config_data: dict[str, Any],
        KLINE_DATA_MAP,
    ) -> tuple[bool, dict[Any, Any], list[Any]]:
        """在行情来源变化时清空 Sheet 缓存，再委托单品执行器计算。"""
        cached_combination = cache_parameters.get("combination") or {}
        if cached_combination and not self._is_same_kline_source(combination, cached_combination):
            cache_parameters["combination"] = {}
        return super()._execute_parameter_combination(
            column_A_length,
            combination,
            cache_parameters,
            config_data,
            KLINE_DATA_MAP,
        )

    def _get_kline_by_date_range(
        self,
        stock_code: str,
        market_type: str,
        start_date: str,
        end_date: str,
        *,
        price_mode: str = "vwap_price",
        adjust_type: str | None = None,
        data_source: str = "dfcf",
        exchange_market: str | None = None,
    ) -> list[dict[str, Any]]:
        """按日期范围获取并投影产品 K 线，统一处理市场和价格字段。"""
        price_field = {
            "kp_price": "stock_kp",
            "sp_price": "stock_sp",
            "vwap_price": "stock_vwap",
        }.get(price_mode, "stock_vwap")
        market_type = normalize_market_type(market_type)
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])
        year_count = max(1, end_year - start_year + 1)
        limit = max(300, year_count * (250 if market_type == "cn" else 252) + 120)

        # 旧的 DFCF/Yahoo 分支保留为注释参考；多品回测也统一走 KlineService。

        #     resolved_code, market = self._resolve_cn_stock_quote(stock_code)
        #     klines = self.dfcf_api.get_stock_kline_data(resolved_code, market, limit, adjust_type=adjust_type)
        # elif price_mode == "vwap_price":
        #     resolved_code, market = self._resolve_dfcf_stock_quote(stock_code)
        #     klines = self.dfcf_api.get_stock_kline_data(resolved_code, market, limit, adjust_type=adjust_type)
        # else:
        #     klines = self.YF_api.get_kline_data(stock_code, "10y", adjust_type=adjust_type)

        klines = self.kline_service.get_kline_data(
            stock_code,
            market_type,
            limit,
            data_source=data_source,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            exchange_market=exchange_market,
        )

        if not klines:
            raise ValueError(f"股票 {stock_code} 没有 K 线数据")
        data_start_date = klines[0]["stock_date"]
        data_end_date = klines[-1]["stock_date"]
        if start_date < data_start_date or end_date > data_end_date:
            raise ValueError(
                f"股票{stock_code} 设定区间 [{start_date}, {end_date}] "
                f"不在K线数据范围 [{data_start_date}, {data_end_date}] 内"
            )
        kline = [
            {"stock_date": item["stock_date"], "stock_val": item[price_field]}
            for item in klines
            if start_date <= item["stock_date"] <= end_date
        ]
        if len(kline) < 100:
            raise ValueError(f"股票{stock_code} 数据量不足，K线数据量小于100条")
        return kline


def build_multi_product_global_preview_payload(
    task_id: str,
    ratios_override: list[Any] | None = None,
) -> dict[str, Any] | None:
    """构建多品回测全局预览所需的聚合数据。"""
    task = _task_repository.get(task_id)
    if not task or task.get("task_type") != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        return None
    config = normalize_multi_product_config(task.get("config") or {})
    products = config["products"]
    if ratios_override is not None:
        if len(ratios_override) != len(products):
            raise ValueError("比例数量与产品数量不一致")
        for product, ratio in zip(products, ratios_override):
            product["ratio"] = normalize_ratio_display(
                ratio.get("ratio") if isinstance(ratio, dict) else ratio
            )
    results = _sort_task_results(
        _task_result_repository.list_task_results(task_id)
    )
    cache_key = _global_preview_cache_key(task_id, products, results)
    cached_payload = _get_global_preview_cache(cache_key)
    if cached_payload is not None:
        return cached_payload

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    success_count = 0
    failed_count = 0

    for result in results:
        parameters = _parse_json(result.parameters, {})
        group_index = int(parameters.get("parameter_group_index") or 0)
        group_key = str(group_index)
        group = groups.setdefault(group_key, {
            "group_key": group_key,
            "group_label": f"参数方案 {group_index + 1}",
            "parameter_group_index": group_index,
            "products": products,
            "product_results": {},
            "failed_results": 0,
        })
        product_index = int(parameters.get("product_index") or 0)
        if not result.success:
            failed_count += 1
            group["failed_results"] += 1
            continue
        success_count += 1
        core = _extract_result_core(result)
        calculate_metrics = (
            (core.get("calculate_metrics") or core.get("analyze_result"))
            if isinstance(core, dict)
            else {}
        )
        weighted_calculate_metrics = core.get("weighted_calculate_metrics") if isinstance(core, dict) else {}
        group["product_results"][product_index] = {
            "result_id": result.id,
            "step_index": result.step_index,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "parameters": parameters,
            "metrics": _derive_metrics(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "return_date": _get_return_date_for_task_result(result),
            "weighted_metrics": (
                _derive_metrics(weighted_calculate_metrics)
                if isinstance(weighted_calculate_metrics, dict) and weighted_calculate_metrics
                else {}
            ),
        }

    serialized_groups = []
    for group in groups.values():
        portfolio_metrics = _derive_metrics(_build_portfolio_metrics(group["product_results"], products))
        weighted_metrics_by_product: dict[int, dict[str, Any]] = {}
        metrics_by_product: dict[int, dict[str, Any]] = {}
        for product in products:
            product_index = int(product["product_index"])
            product_result = group["product_results"].get(product_index) or {}
            metrics_by_product[product_index] = product_result.get("metrics") or {}
            weighted_metrics = product_result.get("weighted_metrics") or {}
            current_ratio = (products[product_index] if product_index < len(products) else {}).get("ratio")
            saved_ratio = str((product_result.get("parameters") or {}).get("ratio") or "").strip()
            if not weighted_metrics or saved_ratio != str(current_ratio or "").strip():
                weighted_metrics = _derive_metrics(
                    _build_weighted_product_metrics(
                        product_result.get("return_date") or [],
                        current_ratio,
                    )
                )
                product_result["weighted_metrics"] = weighted_metrics
            weighted_metrics_by_product[product_index] = weighted_metrics

        rows = []
        for category, metric, index_key, result_key, value_type in SUMMARY_ROW_DEFS:
            product_values = []
            for product in products:
                product_index = int(product["product_index"])
                metrics = metrics_by_product.get(product_index) or {}
                weighted_metrics = weighted_metrics_by_product.get(product_index) or {}
                index_value = metrics.get(index_key) if index_key else None
                result_value = metrics.get(result_key) if result_key else None
                product_values.append({
                    "product_index": product_index,
                    "index_value": _fmt_value(index_value, value_type) if index_key else "-",
                    "result_value": _fmt_value(result_value, value_type),
                    "weighted_result_value": _fmt_value(
                        weighted_metrics.get(result_key),
                        value_type,
                    ),
                    "raw_index_value": index_value,
                    "raw_result_value": result_value,
                    "raw_weighted_index_value": weighted_metrics.get(index_key) if index_key else None,
                    "raw_weighted_result_value": weighted_metrics.get(result_key),
                })
            weighted_index_value = portfolio_metrics.get(index_key) if index_key else None
            weighted_result_value = portfolio_metrics.get(result_key) if result_key else None
            rows.append({
                "category": category,
                "metric": metric,
                "value_type": value_type,
                "product_values": product_values,
                "weighted_index_value": (
                    _fmt_value(weighted_index_value, value_type)
                    if index_key and weighted_index_value is not None
                    else "-"
                ),
                "weighted_result_value": (
                    _fmt_value(weighted_result_value, value_type)
                    if weighted_result_value is not None
                    else "-"
                ),
                "raw_weighted_index_value": weighted_index_value,
                "raw_weighted_result_value": weighted_result_value,
            })
        serialized_groups.append({
            **{key: value for key, value in group.items() if key != "product_results"},
            "rows": rows,
            "result_count": len(group["product_results"]),
        })

    payload = {
        "task": {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "start_date": config["start_date"],
            "end_date": config["end_date"],
        },
        "summary": {
            "total_results": len(results),
            "success_results": success_count,
            "failed_results": failed_count,
            "group_count": len(serialized_groups),
            "product_count": len(products),
        },
        "products": products,
        "groups": serialized_groups,
    }
    _set_global_preview_cache(cache_key, payload)
    return payload
