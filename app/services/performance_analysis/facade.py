"""V1 指标统一门面。

所有业务入口先把输入规范化为累计收益行，再由此门面调用唯一的 V1
指标计算器。``metrics.py`` 负责公式，门面负责统一结果对象和字段分组。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import pandas as pd

from app.services.performance_analysis.historical_metrics import find_all_entry as _all_entry
from app.services.performance_analysis.response_dto import MetricsV1Result
from app.utils.value_parser import _convert_pandas_to_native


SCHEMA_VERSION = "metrics.v1"


def _first_value(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _frame_date(frame: Any, first: bool) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "date" not in frame:
        return None
    value = frame["date"].iloc[0 if first else -1]
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _total_drawdown(metrics: dict[str, Any], key: str) -> Any:
    payload = metrics.get(key) or {}
    total = payload.get("total_maximum_drawdown") if isinstance(payload, dict) else None
    return total.get("drawdown") if isinstance(total, dict) else None


def _canonical_metrics(
    metrics: dict[str, Any],
    index_df: pd.DataFrame | None = None,
    start_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """把完整 V1 字典投影为统一分组，同时保留完整指标。"""
    index_sharpe = (metrics.get("index_sharpe_ratios") or {}).get("all") or {}
    start_sharpe = (metrics.get("start_sharpe_ratios") or {}).get("all") or {}
    index_sortino = _all_entry(metrics.get("index_sortino_ratio"))
    start_sortino = _all_entry(metrics.get("start_sortino_ratio"))
    excess_return = metrics.get("excess_cumulative_return")
    excess_nav = metrics.get("excess_nav")
    if excess_nav is None and isinstance(excess_return, (int, float)) and math.isfinite(excess_return):
        excess_nav = 1 + excess_return
    return {
        "schema_version": SCHEMA_VERSION,
        "period": {"start": _frame_date(index_df, True), "end": _frame_date(index_df, False)},
        "benchmark": {
            "cumulative_return": metrics.get("index_cumulative_return"),
            "annualized_return": _first_value(
                _all_entry(metrics.get("index_annualized_rates")).get("annualized_return"),
                metrics.get("index_annualized_return"),
            ),
            "max_drawdown": _total_drawdown(metrics, "index_maximum_drawdown"),
            "sharpe_ratio": index_sharpe.get("sharpe_ratio"),
            "sortino_ratio": index_sortino.get("sortino_ratio"),
        },
        "strategy": {
            "cumulative_return": metrics.get("start_cumulative_return"),
            "annualized_return": _first_value(
                _all_entry(metrics.get("start_annualized_rates")).get("annualized_return"),
                metrics.get("start_annualized_return"),
            ),
            "max_drawdown": _total_drawdown(metrics, "start_maximum_drawdown"),
            "sharpe_ratio": start_sharpe.get("sharpe_ratio"),
            "sortino_ratio": start_sortino.get("sortino_ratio"),
        },
        "relative": {
            "cumulative_excess_return": excess_return,
            "excess_nav": excess_nav,
            "annualized_return": _all_entry(metrics.get("excess_returns")).get("annualized_return_diff"),
            "excess_sharpe": metrics.get("excess_sharpe"),
            "excess_sortino": metrics.get("excess_sortino"),
        },
        "distributions": {
            "benchmark_daily": metrics.get("index_days_distribution"),
            "strategy_daily": metrics.get("start_days_distribution"),
            "benchmark_monthly": metrics.get("index_monthly_distribution"),
            "strategy_monthly": metrics.get("start_monthly_distribution"),
            "excess_monthly": metrics.get("excess_distribution"),
        },
        "all_metrics": metrics,
    }


def build_series_payload(result: "MetricsV1Result | None") -> dict[str, Any] | None:
    """从 V1 计算结果导出净值序列（analyze 请求带 include_series=true 时下发）。

    index/start/excess 三帧由同一 base_df 派生，日期轴天然一致，只导出一份 dates；
    单列模式（无基准）没有这些帧，返回 None。净值保留 6 位小数、非有限值置 None，
    与 metrics 出口的 _convert_pandas_to_native 口径一致。
    """
    if result is None:
        return None
    frames = (result.index_df, result.start_df, result.excess_df)
    if not all(isinstance(frame, pd.DataFrame) and not frame.empty for frame in frames):
        return None
    index_df, start_df, excess_df = frames

    dates = [value.strftime("%Y-%m-%d") for value in pd.to_datetime(index_df["date"])]

    def _nav(frame: pd.DataFrame) -> list[float | None]:
        values: list[float | None] = []
        for value in frame["net_value"]:
            number = float(value) if pd.notna(value) else None
            if number is not None and math.isfinite(number):
                values.append(round(number, 6))
            else:
                values.append(None)
        return values

    return {
        "dates": dates,
        "index_nav": _nav(index_df),
        "start_nav": _nav(start_df),
        "excess_nav": _nav(excess_df),
    }


def calculate_v1_metrics(
    returns: Iterable[dict[str, Any]],
    *,
    runtime_params: Any = None,
    analyzer: Any = None,
) -> MetricsV1Result:
    """根据累计收益行计算统一的 V1 结果。"""
    if analyzer is None:
        from app.services.performance_analysis.analyzer import performance_analyzer

        analyzer = performance_analyzer
    calculated = analyzer._calculate_metrics_v1(
        list(returns or []),
        return_dataframes=True,
        runtime_params=runtime_params,
    )
    if not isinstance(calculated, tuple) or len(calculated) != 4:
        raise ValueError("V1 指标计算器返回结构无效")
    raw_metrics, index_df, start_df, excess_df = calculated
    if not raw_metrics:
        raise ValueError("收益数据无法生成 V1 指标")
    metrics = _convert_pandas_to_native(raw_metrics)
    canonical = _convert_pandas_to_native(_canonical_metrics(metrics, index_df, start_df))
    return MetricsV1Result(
        schema_version=SCHEMA_VERSION,
        metrics=metrics,
        canonical_metrics=canonical,
        index_df=index_df,
        start_df=start_df,
        excess_df=excess_df,
    )

