"""历史指标载荷读取工具。

本模块只提供读取期投影与缺失指标补全，不再兼容旧字段名。
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from typing import Any

from app.utils.json_utils import dumps


def find_all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    """从年度明细列表中取 ``year == 'all'`` 的汇总条目；无则返回空 dict。"""
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def metric_year_key(value: Any) -> str:
    """指标年度键归一（multi/report_query 两份拷贝收敛）：all→""，整型浮点转 int。"""
    text = str(value if value is not None else "").strip()
    if not text or text.lower() == "all":
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def avg_monthly_excess_return_diff(calculate_metrics: Any) -> float | None:
    """月超额收益差（monthly_excess_return_diff）的算术均值；无有效月份返回 None。

    multi/report_query/extractor 的同构拷贝收敛于此。
    """
    monthly_excess_returns = (calculate_metrics or {}).get("monthly_excess_returns") or []
    values = [
        item.get("monthly_excess_return_diff")
        for item in monthly_excess_returns
        if isinstance(item, dict) and item.get("monthly_excess_return_diff") is not None
    ]
    return sum(values) / len(values) if values else None


def collect_summary_all_entries(metrics: Any) -> dict[str, Any]:
    """一次收集汇总投影所需的全部 ``year=='all'`` 条目与 sharpe 'all' 表
    （ponytail 审计 B2：multi/report_query/extractor 三处查找管道收敛）。

    数值容差、键回退与格式化仍由各投影点自行决定——本函数只负责取条目。
    """
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "excess_all": find_all_entry(metrics.get("excess_returns")),
        "index_profit_monthly_all": find_all_entry(metrics.get("index_profit_monthly")),
        "start_profit_monthly_all": find_all_entry(metrics.get("start_profit_monthly")),
        "index_kama_all": find_all_entry(metrics.get("index_kama_ratio")),
        "start_kama_all": find_all_entry(metrics.get("start_kama_ratio")),
        "index_sortino_all": find_all_entry(metrics.get("index_sortino_ratio")),
        "start_sortino_all": find_all_entry(metrics.get("start_sortino_ratio")),
        "monthly_excess_percentage_all": find_all_entry(
            metrics.get("monthly_excess_return_percentage")
        ),
        "index_sharpe_all": (metrics.get("index_sharpe_ratios") or {}).get("all") or {},
        "start_sharpe_all": (metrics.get("start_sharpe_ratios") or {}).get("all") or {},
    }


def derive_year_max_excess_drawdown(calculate_metrics, parse_number, year_key, *, direction: int = 1):
    """年度"超额回撤优势"最大值（ponytail 审计 B6 合并 multi/report_query 两份拷贝）。

    仅统计年超额收益为正的年份。direction=1 返回 ``指数年回撤 − 策略年回撤``
    （正值"跌幅优势"，多品预览契约）；direction=-1 返回 ``策略 − 指数``
    （报告展示契约）。
    """
    annual_excess_returns = [
        (year_key(item.get("year")), parse_number(item.get("annualized_return_diff")))
        for item in calculate_metrics.get("excess_returns") or []
        if isinstance(item, dict)
    ]
    annual_excess_returns = [(year, diff) for year, diff in annual_excess_returns if year]
    if not annual_excess_returns:
        return None

    excess_years = {
        year
        for year, annualized_return_diff in annual_excess_returns
        if isinstance(annualized_return_diff, (int, float))
        and math.isfinite(annualized_return_diff)
        and annualized_return_diff > 0
    }
    if not excess_years:
        return 0.0

    index_max_dd = calculate_metrics.get("index_maximum_drawdown") or {}
    start_max_dd = calculate_metrics.get("start_maximum_drawdown") or {}
    index_year_map = {
        year: item
        for item in index_max_dd.get("year_maximum_drawdown", [])
        if isinstance(item, dict)
        for year in [year_key(item.get("year"))]
        if year in excess_years
    }
    start_year_map = {
        year: item
        for item in start_max_dd.get("year_maximum_drawdown", [])
        if isinstance(item, dict)
        for year in [year_key(item.get("year"))]
        if year in excess_years
    }

    diffs = []
    for year, index_item in index_year_map.items():
        start_item = start_year_map.get(year) or {}
        index_drawdown = parse_number(index_item.get("drawdown"))
        start_drawdown = parse_number(start_item.get("drawdown"))
        if not isinstance(index_drawdown, (int, float)) or not isinstance(start_drawdown, (int, float)):
            continue
        if not math.isfinite(index_drawdown) or not math.isfinite(start_drawdown):
            continue
        diffs.append(direction * (index_drawdown - start_drawdown))
    return max(diffs) if diffs else None

# 固定 20 项全局预览、单结果预览中不能由旧别名恢复的关键指标。
_PREVIEW_REQUIRED_KEYS = (
    "excess_sharpe",
    "excess_sortino",
    "index_sortino_ratio",
    "start_sortino_ratio",
    "year_index_yearly_max_repair_days",
    "year_start_yearly_max_repair_days",
)


def extract_core_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取完整 V1 指标（唯一来源 metrics_payload.metrics）。"""
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    metrics = metrics_payload.get("metrics") if isinstance(metrics_payload, dict) else None
    return metrics if isinstance(metrics, dict) else {}


def _has_preview_metrics(metrics: dict[str, Any]) -> bool:
    return all(metrics.get(key) is not None for key in _PREVIEW_REQUIRED_KEYS)


# 历史结果预览指标的重算缓存：重算对同一收益序列是确定性的（收益序列与存量
# 指标落库后不再变），但"不写入历史 TaskResult"意味着每次预览/导出都会重付
# 一次完整 V1 计算。进程级 LRU 以 (序列 id, 存量指标指纹) 为键，命中返回共享
# 对象，调用方不得改写。
_PREVIEW_METRICS_CACHE_MAX = 512
_preview_metrics_cache: "OrderedDict[Any, dict[str, Any]]" = OrderedDict()
_preview_metrics_cache_lock = threading.Lock()


def _preview_metrics_cache_key(return_series_id: Any, metrics: dict[str, Any]):
    """缓存键带存量指标指纹：历史上同一收益序列可能挂多条结果，重算合并
    依赖各结果自己的存量指标，指纹不同即为不同条目。"""
    digest = hashlib.sha256(dumps(metrics or {}).encode("utf-8")).hexdigest()
    return (return_series_id, digest)


def resolve_preview_metrics(
    core: Any,
    *,
    return_rows: list[dict[str, Any]] | None = None,
    cache_key: Any = None,
) -> dict[str, Any]:
    """返回预览可用指标，不写入历史 TaskResult。

    优先返回已持久化的指标（含历史别名升级）。仅当预览必需指标缺失且能
    从 ``TaskResultReturn`` 或旧 result 内嵌数据取得至少两条收益记录时，
    才按当前 V1 口径临时重算。无收益序列时绝不覆盖已存历史指标。

    cache_key（通常为 return_series_id）提供时启用进程级 LRU 缓存。
    """
    if cache_key is None:
        return _resolve_preview_metrics_uncached(core, return_rows=return_rows)

    key = _preview_metrics_cache_key(cache_key, extract_core_metrics(core))
    with _preview_metrics_cache_lock:
        cached = _preview_metrics_cache.get(key)
        if cached is not None:
            _preview_metrics_cache.move_to_end(key)
            return cached

    resolved = _resolve_preview_metrics_uncached(core, return_rows=return_rows)
    with _preview_metrics_cache_lock:
        _preview_metrics_cache[key] = resolved
        _preview_metrics_cache.move_to_end(key)
        while len(_preview_metrics_cache) > _PREVIEW_METRICS_CACHE_MAX:
            _preview_metrics_cache.popitem(last=False)
    return resolved


def _resolve_preview_metrics_uncached(
    core: Any,
    *,
    return_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = extract_core_metrics(core)
    if _has_preview_metrics(metrics):
        return metrics

    rows = list(return_rows or [])
    if not rows:
        from app.utils.return_series import extract_return_rows

        rows = extract_return_rows(core)
    if len(rows) < 2:
        return metrics

    try:
        from app.services.performance_analysis.facade import calculate_v1_metrics

        recalculated = calculate_v1_metrics(rows).metrics
    except (TypeError, ValueError, KeyError):
        # 兼容层不得因坏序列让原本可展示的历史指标消失。
        return metrics

    # 完整重算指标为当前 V1 口径；但保留历史指标中 V1 没有的业务字段。
    # 对于重算出的非有限值（如超额索提诺分母为零），保留原历史有限值。
    # 注意 calculate_v1_metrics 出口已把 NaN/inf 转成 None（non_finite_to_none），
    # 守卫必须同时挡 None，否则重算失败的空值会覆盖历史有限值。
    merged = dict(metrics)
    for key, value in recalculated.items():
        if value is None:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        merged[key] = value
    return merged


def extract_core_weighted_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取比例后单品指标（唯一来源 metrics_payload.weighted_metrics）。"""
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    weighted = metrics_payload.get("weighted_metrics") if isinstance(metrics_payload, dict) else None
    return weighted if isinstance(weighted, dict) else {}
