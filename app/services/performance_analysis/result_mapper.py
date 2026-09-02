"""绩效分析结果适配组件。

负责调用指标计算并将原始结果整理为页面、报告等消费者需要的扁平字段、
指标字典和 DataFrame 组合；不承担具体指标公式计算。
"""
import json
import math
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.response_dto import MetricsV1ResponseDTO
from app.utils.value_parser import _convert_pandas_to_native


class LegacyMetricsAdapter:
    """将完整 V1 指标投影为 C 系列使用的扁平结果。"""

    @staticmethod
    def to_flat(metrics: dict[str, Any]) -> dict[str, Any]:
        """从标准指标字典提取旧接口所需的核心字段。"""
        def all_entry(value: Any) -> dict[str, Any]:
            if isinstance(value, list):
                return next((item for item in value if isinstance(item, dict) and str(item.get("year")) == "all"), {})
            return {}

        index_sharpe = (metrics.get("index_sharpe_ratios") or {}).get("all") or {}
        start_sharpe = (metrics.get("start_sharpe_ratios") or {}).get("all") or {}
        index_sortino = all_entry(metrics.get("index_sortino_ratio"))
        start_sortino = all_entry(metrics.get("start_sortino_ratio"))
        excess_all = all_entry(metrics.get("excess_returns"))
        index_dd = (metrics.get("index_maximum_drawdown") or {}).get("total_maximum_drawdown") or {}
        start_dd = (metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown") or {}
        return {
            "index_annualized_return": excess_all.get("index_annualized_return"),
            "start_annualized_return": excess_all.get("start_annualized_return"),
            "index_profit_annual": metrics.get("index_profit_annual"),
            "start_profit_annual": metrics.get("start_profit_annual"),
            "index_profit_monthly_percentage": (next((x for x in metrics.get("index_profit_monthly", []) if str(x.get("year")) == "all"), {}) or {}).get("profit_monthly_percentage"),
            "start_profit_monthly_percentage": (next((x for x in metrics.get("start_profit_monthly", []) if str(x.get("year")) == "all"), {}) or {}).get("profit_monthly_percentage"),
            "index_avg_monthly_return": index_sharpe.get("avg_monthly_return"),
            "start_avg_monthly_return": start_sharpe.get("avg_monthly_return"),
            "index_monthly_std_dev": index_sharpe.get("monthly_std_dev"),
            "start_monthly_std_dev": start_sharpe.get("monthly_std_dev"),
            "index_annual_std_dev": index_sharpe.get("annual_std_dev"),
            "start_annual_std_dev": start_sharpe.get("annual_std_dev"),
            "index_monthly_return_volatility": metrics.get("index_monthly_return_volatility"),
            "start_monthly_return_volatility": metrics.get("start_monthly_return_volatility"),
            "annualized_return_diff": excess_all.get("annualized_return_diff"),
            "outperform_year": metrics.get("outperform_year"),
            "monthly_excess_return_percentage_last_return": (next((x for x in metrics.get("monthly_excess_return_percentage", []) if str(x.get("year")) == "all"), {}) or {}).get("excess_return"),
            "avg_monthly_excess_returns": metrics.get("average_monthly_excess_return"),
            "monthly_excess_volatility": metrics.get("monthly_excess_volatility"),
            "start_drawdown": start_dd.get("drawdown"),
            "index_sharpe_ratio": index_sharpe.get("sharpe_ratio"),
            "start_sharpe_ratio": start_sharpe.get("sharpe_ratio"),
            "index_kama_ratio": (all_entry(metrics.get("index_kama_ratio")) or {}).get("kama_ratio"),
            "start_kama_ratio": (all_entry(metrics.get("start_kama_ratio")) or {}).get("kama_ratio"),
            "index_sortino_ratio": index_sortino.get("sortino_ratio"),
            "start_sortino_ratio": start_sortino.get("sortino_ratio"),
            "excess_sharpe": metrics.get("excess_sharpe"),
            "excess_sortino": metrics.get("excess_sortino"),
        }


class PerformanceResultMapperMixin:
    def get_return_analysis_v1(self, data: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        基于与 get_calculate_metrics_v1 相同的 return 列表结构，
        返回 (扁平化旧字段投影, 统一存储载荷)。

        第二个返回值是 ``MetricsV1Result.to_json_dict(include_series=False)``：
        {"schema_version", "metrics", "canonical_metrics"}，供 TaskResult
        统一持久化；完整收益序列仍由 TaskResultReturn 单独存储。

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

        from app.services.performance_analysis.facade import calculate_v1_metrics

        canonical_result = calculate_v1_metrics(data, analyzer=self)
        analyze_result = canonical_result.metrics
        metrics_payload = canonical_result.to_json_dict(include_series=False)
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
            "index_sortino_ratio": 0,
            "start_sortino_ratio": 0,
            "excess_sharpe": 0,
            "excess_sortino": 0,
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
        result["excess_sharpe"] = safe_value(analyze_result.get("excess_sharpe"))
        result["excess_sortino"] = safe_value(analyze_result.get("excess_sortino"))

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

        index_sortino_ratio_all = pick_all(analyze_result.get("index_sortino_ratio"))
        start_sortino_ratio_all = pick_all(analyze_result.get("start_sortino_ratio"))
        result["index_sortino_ratio"] = safe_value(index_sortino_ratio_all.get("sortino_ratio"))
        result["start_sortino_ratio"] = safe_value(start_sortino_ratio_all.get("sortino_ratio"))

        return result, metrics_payload

    def get_calculate_metrics_v1(self, data, runtime_params=None):
        """执行 V1 格式数据的指标计算。"""
        from app.services.performance_analysis.facade import calculate_v1_metrics

        # 所有新调用统一经过 V1 指标门面。
        result = calculate_v1_metrics(data, runtime_params=runtime_params, analyzer=self).metrics

        # 将结果转换为 JSON，处理 Pandas 类型
        if isinstance(result, pd.DataFrame):
            return result.to_json(orient='records', date_format='iso', force_ascii=False)
        elif isinstance(result, pd.Series):
            return result.to_json(date_format='iso', force_ascii=False)
        elif isinstance(result, dict):
            # 处理字典中可能包含的 Pandas 类型
            return _convert_pandas_to_native(result)
        else:
            return result


    def get_calculate_metrics_v1_with_dataframes(
        self,
        returns: List[Dict[str, Any]],
        runtime_params: MetricsRuntimeParamsDTO | None = None,
    ) -> MetricsV1ResponseDTO:
        """返回 V1 指标，以及指数、策略和超额收益序列。

        ``runtime_params`` 控制市场下跌、上涨阶段的判定阈值（7.1/7.2）。
        """
        from app.services.performance_analysis.facade import calculate_v1_metrics

        result = calculate_v1_metrics(
            returns,
            runtime_params=runtime_params,
            return_dataframes=True,
            analyzer=self,
        )
        return MetricsV1ResponseDTO(
            metrics=result.metrics,
            canonical_metrics=result.canonical_metrics,
            index_df=result.index_df,
            start_df=result.start_df,
            excess_df=result.excess_df,
        )
