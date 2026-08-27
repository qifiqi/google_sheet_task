"""Response-shaping adapters for performance-analysis consumers."""

import math
from typing import Any, Dict, List, Tuple

from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.response_dto import MetricsV1ResponseDTO


class PerformanceResultMapperMixin:
    def get_return_analysis_v1(self, data: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        基于与 get_calculate_metrics_v1 相同的 return 列表结构，
        返回扁平化结构结果。

        入参示例:
        [
            {
                "date": "2026-01-02",
                "index_return": 0.0123,
                "start_return": 0.0156,
            }
        ]
        """
        if not data:
            return {}, {}

        analyze_result = self._calculate_metrics_v1(data)
        if not analyze_result:
            return {}, {}

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
            "index_sotino_ratio": 0,
            "start_sotino_ratio": 0,
            "excess_sharp": 0,
            "excess_of_promissory_note": 0,
        }

        def pick_all(items, key="year", value="all"):
            """从筛选项中选取指定年份或 all 对应的全部值。"""
            if not isinstance(items, list):
                return {}
            for item in items:
                if isinstance(item, dict) and item.get(key) == value:
                    return item
            return {}

        def safe_value(value):
            """将空值和非有限浮点数转换为可 JSON 序列化的空值。"""
            if value is None:
                return 0
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return 0
            return value

        excess_returns = analyze_result.get("excess_returns") or []
        excess_return_all = pick_all(excess_returns)
        result["index_annualized_return"] = safe_value(excess_return_all.get("index_annualized_return"))
        result["start_annualized_return"] = safe_value(excess_return_all.get("start_annualized_return"))
        result["annualized_return_diff"] = safe_value(excess_return_all.get("annualized_return_diff"))

        result["index_profit_annual"] = safe_value(analyze_result.get("index_profit_annual"))
        result["start_profit_annual"] = safe_value(analyze_result.get("start_profit_annual"))
        result["outperform_year"] = safe_value(analyze_result.get("outperform_year"))
        result["monthly_excess_volatility"] = safe_value(analyze_result.get("monthly_excess_volatility"))
        result["excess_drawdown_winning_rate"] = safe_value(analyze_result.get("excess_drawdown_winning_rate"))
        result["start_maximum_number_of_backtest_repair_days"] = safe_value(
            analyze_result.get("start_maximum_number_of_backtest_repair_days")
        )
        result["excess_maximum_number_of_backtest_repair_days"] = safe_value(
            analyze_result.get("excess_maximum_number_of_backtest_repair_days")
        )
        result["excess_sharp"] = safe_value(analyze_result.get("excess_sharp"))
        result["excess_of_promissory_note"] = safe_value(analyze_result.get("excess_of_promissory_note"))

        index_profit_monthly_all = pick_all(analyze_result.get("index_profit_monthly"))
        start_profit_monthly_all = pick_all(analyze_result.get("start_profit_monthly"))
        result["index_profit_monthly_percentage"] = safe_value(
            index_profit_monthly_all.get("profit_monthly_percentage")
        )
        result["start_profit_monthly_percentage"] = safe_value(
            start_profit_monthly_all.get("profit_monthly_percentage")
        )

        monthly_excess_return_percentage_all = pick_all(analyze_result.get("monthly_excess_return_percentage"))
        result["monthly_excess_return_percentage_last_return"] = safe_value(
            monthly_excess_return_percentage_all.get("excess_return")
        )

        index_sharpe_ratios_all = (analyze_result.get("index_sharpe_ratios") or {}).get("all") or {}
        start_sharpe_ratios_all = (analyze_result.get("start_sharpe_ratios") or {}).get("all") or {}
        result["index_avg_monthly_return"] = safe_value(index_sharpe_ratios_all.get("avg_monthly_return"))
        result["start_avg_monthly_return"] = safe_value(start_sharpe_ratios_all.get("avg_monthly_return"))
        result["index_avg_monthly_return_common"] = result["index_avg_monthly_return"]
        result["start_avg_monthly_return_common"] = result["start_avg_monthly_return"]
        result["index_monthly_std_dev"] = safe_value(index_sharpe_ratios_all.get("monthly_std_dev"))
        result["start_monthly_std_dev"] = safe_value(start_sharpe_ratios_all.get("monthly_std_dev"))
        result["index_annual_std_dev"] = safe_value(index_sharpe_ratios_all.get("annual_std_dev"))
        result["start_annual_std_dev"] = safe_value(start_sharpe_ratios_all.get("annual_std_dev"))
        result["index_monthly_return_volatility"] = safe_value(analyze_result.get("index_monthly_return_volatility"))
        result["start_monthly_return_volatility"] = safe_value(analyze_result.get("start_monthly_return_volatility"))
        result["index_sharpe_ratio"] = safe_value(index_sharpe_ratios_all.get("sharpe_ratio"))
        result["start_sharpe_ratio"] = safe_value(start_sharpe_ratios_all.get("sharpe_ratio"))

        monthly_excess_returns = analyze_result.get("monthly_excess_returns") or []
        if monthly_excess_returns:
            avg_monthly_excess_returns = sum(
                safe_value(item.get("monthly_excess_return_diff"))
                for item in monthly_excess_returns
                if isinstance(item, dict)
            ) / len(monthly_excess_returns)
            result["avg_monthly_excess_returns"] = safe_value(avg_monthly_excess_returns)

        index_maximum_drawdown = analyze_result.get("index_maximum_drawdown") or {}
        start_maximum_drawdown = analyze_result.get("start_maximum_drawdown") or {}
        year_excess_returns = [
            int(item["year"])
            for item in excess_returns
            if isinstance(item, dict)
               and item.get("year") != "all"
               and safe_value(item.get("annualized_return_diff")) > 0
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
                safe_value(start_item.get("drawdown")) - safe_value(index_item.get("drawdown"))
            )
        if max_drawdown_list:
            result["max_drawdown"] = safe_value(max(max_drawdown_list))

        total_maximum_drawdown = start_maximum_drawdown.get("total_maximum_drawdown") or {}
        result["start_drawdown"] = safe_value(total_maximum_drawdown.get("drawdown"))

        index_kama_ratio_all = pick_all(analyze_result.get("index_kama_ratio"))
        start_kama_ratio_all = pick_all(analyze_result.get("start_kama_ratio"))
        result["index_kama_ratio"] = safe_value(index_kama_ratio_all.get("kama_ratio"))
        result["start_kama_ratio"] = safe_value(start_kama_ratio_all.get("kama_ratio"))

        index_sotino_ratio_all = pick_all(analyze_result.get("index_sotino_ratio"))
        start_sotino_ratio_all = pick_all(analyze_result.get("start_sotino_ratio"))
        result["index_sotino_ratio"] = safe_value(index_sotino_ratio_all.get("sotino_ratio"))
        result["start_sotino_ratio"] = safe_value(start_sotino_ratio_all.get("sotino_ratio"))

        return result, analyze_result

    def get_calculate_metrics_v1(self, data):
        """执行 V1 格式数据的指标计算。"""
        return self._calculate_metrics_v1(data)

    def get_calculate_metrics_v1_with_dataframes(
        self,
        returns: List[Dict[str, Any]],
        runtime_params: MetricsRuntimeParamsDTO | None = None,
    ) -> MetricsV1ResponseDTO:
        """返回 V1 指标，以及指数、策略和超额收益序列。

        ``runtime_params`` 作为后续市场阶段指标的配置入口，当前暂不应用其中的阈值。
        """
        _ = runtime_params
        metrics, index_df, start_df, excess_df = self._calculate_metrics_v1(
            returns,
            return_dataframes=True,
        )
        return MetricsV1ResponseDTO(
            metrics=metrics,
            index_df=index_df,
            start_df=start_df,
            excess_df=excess_df,
        )
