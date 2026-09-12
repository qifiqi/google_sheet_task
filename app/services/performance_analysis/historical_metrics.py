"""历史指标载荷读取兼容。

新计算结果只产生标准字段；本模块用于读取数据库中尚未迁移的旧 JSON，
并在预览所需字段缺失且收益序列可用时按当前 V1 口径临时补全。
"""

from __future__ import annotations

import math
from typing import Any


_LEGACY_KEYS = {
    "index_sotino_ratio": "index_sortino_ratio",
    "start_sotino_ratio": "start_sortino_ratio",
    "index_weekly_sotino_ratio": "index_weekly_sortino_ratio",
    "start_weekly_sotino_ratio": "start_weekly_sortino_ratio",
    "sotino_ratio": "sortino_ratio",
    "excess_sharp": "excess_sharpe",
    "excess_of_promissory_note": "excess_sortino",
    "cumulative_excess": "excess_cumulative_return",
    "excess_net": "excess_nav",
}


def find_all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    """从年度明细列表中取 ``year == 'all'`` 的汇总条目；无则返回空 dict。"""
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


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


def upgrade_historical_metrics(value: Any) -> Any:
    """读取旧指标 JSON 时转换为当前字段名；新写入路径不要调用旧键回退。"""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = _LEGACY_KEYS.get(str(key), key)
            result[normalized_key] = upgrade_historical_metrics(item)
        return result
    if isinstance(value, list):
        return [upgrade_historical_metrics(item) for item in value]
    return value


def extract_core_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取并标准化完整 V1 指标。

    统一存储载荷（``metrics_payload.metrics``）优先；历史键
    ``calculate_metrics`` / ``analyze_result`` 作为读取回退。无论来源如何，
    均执行旧字段别名升级，确保全局预览、结果预览与导出使用同一字段契约。
    """
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("metrics"), dict):
        return upgrade_historical_metrics(metrics_payload["metrics"])
    legacy = core.get("calculate_metrics") or core.get("analyze_result")
    return upgrade_historical_metrics(legacy) if isinstance(legacy, dict) else {}


def _has_preview_metrics(metrics: dict[str, Any]) -> bool:
    return all(metrics.get(key) is not None for key in _PREVIEW_REQUIRED_KEYS)


def resolve_preview_metrics(
    core: Any,
    *,
    return_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """返回预览可用指标，不写入历史 TaskResult。

    优先返回已持久化的指标（含历史别名升级）。仅当预览必需指标缺失且能
    从 ``TaskResultReturn`` 或旧 result 内嵌数据取得至少两条收益记录时，
    才按当前 V1 口径临时重算。无收益序列时绝不覆盖已存历史指标。
    """
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
    merged = dict(metrics)
    for key, value in recalculated.items():
        if isinstance(value, float) and not math.isfinite(value):
            continue
        merged[key] = value
    return merged


def extract_core_weighted_metrics(core: Any) -> dict[str, Any]:
    """从结果核心字典提取比例后单品指标。

    统一存储载荷（``metrics_payload.weighted_metrics``）优先；历史兄弟键
    ``weighted_calculate_metrics`` 作为读取回退。
    """
    if not isinstance(core, dict):
        return {}
    metrics_payload = core.get("metrics_payload")
    if isinstance(metrics_payload, dict) and isinstance(metrics_payload.get("weighted_metrics"), dict):
        return upgrade_historical_metrics(metrics_payload["weighted_metrics"])
    legacy = core.get("weighted_calculate_metrics")
    return upgrade_historical_metrics(legacy) if isinstance(legacy, dict) else {}
