"""V1 指标读取期投影：把 metrics 树派生为旧扁平字段，不写入结果载荷。"""

from __future__ import annotations

import math
from typing import Any

from app.services.performance_analysis.historical_metrics import find_all_entry


def _safe_value(value: Any) -> Any:
    if value is None:
        return 0
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return 0
    return value


def flatten_v1_metrics(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict) or not metrics:
        return {}

    result = {
        "index_annualized_return": 0,
        "start_annualized_return": 0,
        "index_profit_annual": 0,
        "start_profit_annual": 0,
        "index_profit_monthly_percentage": 0,
        "start_profit_monthly_percentage": 0,
        "index_avg_monthly_return": 0,
        "start_avg_monthly_return": 0,
        "index_avg_monthly_return_common": 0,
        "start_avg_monthly_return_common": 0,
        "index_monthly_std_dev": 0,
        "start_monthly_std_dev": 0,
        "index_annual_std_dev": 0,
        "start_annual_std_dev": 0,
        "index_monthly_return_volatility": 0,
        "start_monthly_return_volatility": 0,
        "annualized_return_diff": 0,
        "outperform_year": 0,
        "monthly_excess_return_percentage_last_return": 0,
        "avg_monthly_excess_returns": 0,
        "monthly_excess_volatility": 0,
        "max_drawdown": 0,
        "excess_drawdown_winning_rate": 0,
        "start_drawdown": 0,
        "start_maximum_number_of_backtest_repair_days": 0,
        "excess_maximum_number_of_backtest_repair_days": 0,
        "index_sharpe_ratio": 0,
        "start_sharpe_ratio": 0,
        "index_kama_ratio": 0,
        "start_kama_ratio": 0,
        "index_sortino_ratio": 0,
        "start_sortino_ratio": 0,
        "excess_sharpe": 0,
        "excess_sortino": 0,
    }

    excess_returns = metrics.get("excess_returns") or []
    excess_return_all = find_all_entry(excess_returns)
    result["index_annualized_return"] = _safe_value(excess_return_all.get("index_annualized_return"))
    result["start_annualized_return"] = _safe_value(excess_return_all.get("start_annualized_return"))
    result["annualized_return_diff"] = _safe_value(excess_return_all.get("annualized_return_diff"))

    for key in (
        "index_profit_annual",
        "start_profit_annual",
        "outperform_year",
        "monthly_excess_volatility",
        "excess_drawdown_winning_rate",
        "start_maximum_number_of_backtest_repair_days",
        "excess_maximum_number_of_backtest_repair_days",
        "excess_sharpe",
        "excess_sortino",
    ):
        result[key] = _safe_value(metrics.get(key))

    index_profit_monthly_all = find_all_entry(metrics.get("index_profit_monthly"))
    start_profit_monthly_all = find_all_entry(metrics.get("start_profit_monthly"))
    result["index_profit_monthly_percentage"] = _safe_value(
        index_profit_monthly_all.get("profit_monthly_percentage")
    )
    result["start_profit_monthly_percentage"] = _safe_value(
        start_profit_monthly_all.get("profit_monthly_percentage")
    )

    monthly_excess_return_percentage_all = find_all_entry(metrics.get("monthly_excess_return_percentage"))
    result["monthly_excess_return_percentage_last_return"] = _safe_value(
        monthly_excess_return_percentage_all.get("excess_return")
    )

    index_sharpe_ratios_all = (metrics.get("index_sharpe_ratios") or {}).get("all") or {}
    start_sharpe_ratios_all = (metrics.get("start_sharpe_ratios") or {}).get("all") or {}
    result["index_avg_monthly_return"] = _safe_value(index_sharpe_ratios_all.get("avg_monthly_return"))
    result["start_avg_monthly_return"] = _safe_value(start_sharpe_ratios_all.get("avg_monthly_return"))
    result["index_avg_monthly_return_common"] = result["index_avg_monthly_return"]
    result["start_avg_monthly_return_common"] = result["start_avg_monthly_return"]
    result["index_monthly_std_dev"] = _safe_value(index_sharpe_ratios_all.get("monthly_std_dev"))
    result["start_monthly_std_dev"] = _safe_value(start_sharpe_ratios_all.get("monthly_std_dev"))
    result["index_annual_std_dev"] = _safe_value(index_sharpe_ratios_all.get("annual_std_dev"))
    result["start_annual_std_dev"] = _safe_value(start_sharpe_ratios_all.get("annual_std_dev"))
    result["index_monthly_return_volatility"] = _safe_value(metrics.get("index_monthly_return_volatility"))
    result["start_monthly_return_volatility"] = _safe_value(metrics.get("start_monthly_return_volatility"))
    result["index_sharpe_ratio"] = _safe_value(index_sharpe_ratios_all.get("sharpe_ratio"))
    result["start_sharpe_ratio"] = _safe_value(start_sharpe_ratios_all.get("sharpe_ratio"))

    monthly_excess_returns = metrics.get("monthly_excess_returns") or []
    if monthly_excess_returns:
        result["avg_monthly_excess_returns"] = _safe_value(
            sum(
                _safe_value(item.get("monthly_excess_return_diff"))
                for item in monthly_excess_returns
                if isinstance(item, dict)
            ) / len(monthly_excess_returns)
        )

    index_maximum_drawdown = metrics.get("index_maximum_drawdown") or {}
    start_maximum_drawdown = metrics.get("start_maximum_drawdown") or {}
    year_excess_returns = [
        int(item["year"])
        for item in excess_returns
        if isinstance(item, dict)
        and item.get("year") != "all"
        and _safe_value(item.get("annualized_return_diff")) > 0
    ]
    index_year_maximum_drawdown = {
        item["year"]: item
        for item in index_maximum_drawdown.get("year_maximum_drawdown", [])
        if isinstance(item, dict) and item.get("year") in year_excess_returns
    }
    start_year_maximum_drawdown = {
        item["year"]: item
        for item in start_maximum_drawdown.get("year_maximum_drawdown", [])
        if isinstance(item, dict) and item.get("year") in year_excess_returns
    }
    max_drawdown_list = []
    for year, index_item in index_year_maximum_drawdown.items():
        start_item = start_year_maximum_drawdown.get(year)
        if not start_item:
            continue
        max_drawdown_list.append(
            _safe_value(start_item.get("drawdown")) - _safe_value(index_item.get("drawdown"))
        )
    if max_drawdown_list:
        result["max_drawdown"] = _safe_value(max(max_drawdown_list))

    total_maximum_drawdown = start_maximum_drawdown.get("total_maximum_drawdown") or {}
    result["start_drawdown"] = _safe_value(total_maximum_drawdown.get("drawdown"))

    result["index_kama_ratio"] = _safe_value(
        find_all_entry(metrics.get("index_kama_ratio")).get("kama_ratio")
    )
    result["start_kama_ratio"] = _safe_value(
        find_all_entry(metrics.get("start_kama_ratio")).get("kama_ratio")
    )
    result["index_sortino_ratio"] = _safe_value(
        find_all_entry(metrics.get("index_sortino_ratio")).get("sortino_ratio")
    )
    result["start_sortino_ratio"] = _safe_value(
        find_all_entry(metrics.get("start_sortino_ratio")).get("sortino_ratio")
    )
    return result
