"""C 系列单品任务的结果载荷字段规格与构建器（2026-09 审计 C4 批次收敛）。

C5/C7 的 `_build_stock_param_result_payload` 中 ~50 行字段块原为逐字复制；
此处以声明式规格 + 构建器收敛，新增指标只改规格表一处。
C4 的单元格地址与取值方式不同（直取不转小数），C3 另有 B6/I15 系语义，
均保留各自任务文件内的映射，不强行并入本规格。
"""

from __future__ import annotations

from typing import Any, Callable

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

# 从 analyze_result（flat_result）直接透传的指标键。
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


def build_analyze_fields(analyze_result: dict[str, Any]) -> dict[str, Any]:
    """从 analyze_result（flat_result）透传次级分析字段。"""
    return {key: analyze_result.get(key, 0) for key in ANALYZE_RESULT_KEYS}
