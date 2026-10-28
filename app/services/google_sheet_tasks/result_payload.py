"""C 系列单品任务的结果载荷字段规格与构建器（2026-09 审计 C4 批次收敛）。

C5/C7 的 `_build_stock_param_result_payload` 中 ~50 行字段块原为逐字复制；
此处以声明式规格 + 构建器收敛，新增指标只改规格表一处。
C4 的单元格地址与取值方式不同（直取不转小数），C3 另有 B6/I15 系语义，
均保留各自任务文件内的映射，不强行并入本规格。
"""

from __future__ import annotations

from typing import Any, Callable

from app.services.performance_analysis.projections import flatten_v1_metrics

# (payload 键, 模板单元格, 变换)；transform="ratio" 表示百分数 → 小数。
STOCK_PARAM_METRIC_SPECS = [
    ("return_rate", "D2", "ratio"),
    ("annualized_rate", "D3", "ratio"),
    ("maxdd", "D4", "ratio"),
    ("index_rate", "D5", "ratio"),
    ("index_annualized_rate", "D6", "ratio"),
    ("max_index_dd", "D7", "ratio"),
    ("fee_total", "D8", "ratio"),
    ("fee_annualized", "D9", "ratio"),
    ("turnover_rate", "D10", None),
    ("return_beats", "D11", "ratio"),
    ("dd_beats", "D12", "ratio"),
    ("max_1y_beats", "D13", "ratio"),
    ("min_1y_beats", "D14", "ratio"),
    ("max_theoretical_leverage", "D15", None),
    ("avg_theoretical_leverage", "D16", None),
    ("unit_theoretical_leverage_return", "D17", "ratio"),
    ("max_actual_leverage", "D18", None),
    ("avg_actual_leverage", "D19", None),
    ("unit_actual_leverage_return", "D20", "ratio"),
]

# 从 metrics_payload.metrics 直接透传的指标键。
ANALYZE_RESULT_KEYS = [
    "start_monthly_std_dev",
    "index_monthly_std_dev",
    "index_annualized_return",
    "start_annualized_return",
    "index_profit_annual",
    "start_profit_annual",
    "index_profit_monthly_percentage",
    "start_profit_monthly_percentage",
    "index_avg_monthly_return_common",
    "start_avg_monthly_return_common",
    "index_monthly_return_volatility",
    "start_monthly_return_volatility",
    "annualized_return_diff",
    "outperform_year",
    "monthly_excess_return_percentage_last_return",
    "avg_monthly_excess_returns",
    "monthly_excess_volatility",
    "max_drawdown",
    "excess_drawdown_winning_rate",
    "start_drawdown",
    "start_maximum_number_of_backtest_repair_days",
    "excess_maximum_number_of_backtest_repair_days",
    "index_sharpe_ratio",
    "start_sharpe_ratio",
    "index_kama_ratio",
    "start_kama_ratio",
    "index_sortino_ratio",
    "start_sortino_ratio",
    "excess_sharpe",
    "excess_sortino",
]


def to_decimal_ratio(value: Any) -> float:
    """Convert percentage-like values into decimal ratios for outbound payloads."""
    if value in (None, ""):
        return 0

    raw_value = value
    if isinstance(value, str):
        raw_value = value.strip().replace("%", "").replace(",", "")
        if raw_value == "":
            return 0

    try:
        return float(raw_value) / 100
    except (TypeError, ValueError):
        return 0


def build_stock_param_metric_fields(value_getter: Callable[[str], Any]) -> dict[str, Any]:
    """按规格表从结果提取模型指标字段。

    value_getter(cell)：C5 传 `result.get(cell, 0)`，C7 传带行偏移的 metric_value。
    """
    fields: dict[str, Any] = {}
    for key, cell, transform in STOCK_PARAM_METRIC_SPECS:
        value = value_getter(cell)
        fields[key] = to_decimal_ratio(value) if transform == "ratio" else value
    return fields


# C1.1 结果块（默认 F2:F26）25 个值按行序的字段规格：
# (payload 键, 变换)；transform="ratio" 表示百分数 → 小数。
# 字段行序与模板结果块一一对应（Start date → 参考x.min），不可调换顺序。
C1_1_RESULT_FIELD_SPECS = [
    ("start_date", None),
    ("end_date", None),
    ("return_rate", "ratio"),
    ("annualized_rate", "ratio"),
    ("maxdd", "ratio"),
    ("maxdd_date", None),
    ("index_rate", "ratio"),
    ("index_annualized_rate", "ratio"),
    ("max_index_dd", "ratio"),
    ("index_max_dd_date", None),
    ("return_beats", "ratio"),
    ("dd_beats", "ratio"),
    ("max_1y_beats", "ratio"),
    ("min_1y_beats", "ratio"),
    ("max_actual_leverage", None),
    ("max_leverage_date", None),
    ("avg_actual_leverage", None),
    ("delvg_count", None),
    ("fee_total", "ratio"),
    ("fee_annualized", "ratio"),
    ("turnover_rate", None),
    ("avg_volatility", "ratio"),
    ("ref_xm", None),
    ("ref_if", None),
    ("ref_x_min", None),
]


def build_c1_1_summary_fields(value_getter: Callable[[int], Any]) -> dict[str, Any]:
    """按行序从 C1.1 结果块提取字段；value_getter(row_offset) 返回第 offset 个结果值。"""
    fields: dict[str, Any] = {}
    for offset, (key, transform) in enumerate(C1_1_RESULT_FIELD_SPECS):
        value = value_getter(offset)
        fields[key] = to_decimal_ratio(value) if transform == "ratio" else value
    return fields


# V1 指标树的结构键（按年列表/字典承载）；出现任一即视为未投影的树输入。
# 扁平投影（flatten_v1_metrics 产物）不含这些键，原样透传不二次扁平。
_V1_TREE_MARKER_KEYS = (
    "excess_returns",
    "index_sharpe_ratios",
    "start_sharpe_ratios",
    "index_maximum_drawdown",
    "start_maximum_drawdown",
    "index_profit_monthly",
    "start_profit_monthly",
    "monthly_excess_return_percentage",
)


def build_analyze_fields(analyze_result: dict[str, Any]) -> dict[str, Any]:
    """从 metrics_payload.metrics 透传次级分析字段。

    V1 指标树中卡玛/索提诺/夏普等为按年列表结构，远端 StockParamResult
    对应字段是 double 标量：树输入先经 flatten_v1_metrics 取 all 窗口标量
    （历史 flat_result 的等价投影；合并曾丢失该层导致推送 400）。
    """
    if any(key in analyze_result for key in _V1_TREE_MARKER_KEYS):
        analyze_result = flatten_v1_metrics(analyze_result)
    return {key: analyze_result.get(key, 0) for key in ANALYZE_RESULT_KEYS}
