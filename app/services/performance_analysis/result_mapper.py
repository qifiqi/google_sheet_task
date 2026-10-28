"""绩效分析结果适配组件。

负责调用指标计算并把结果整理为统一存储载荷；不承担具体指标公式计算。
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.response_dto import MetricsV1Result
from app.utils.value_parser import _convert_pandas_to_native


class PerformanceResultMapperMixin:
    def get_return_analysis_v1(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """返回统一存储载荷 {schema_version, metrics, canonical_metrics}。"""
        if not data:
            return {}

        from app.services.performance_analysis.facade import calculate_v1_metrics

        canonical_result = calculate_v1_metrics(data, analyzer=self)
        return canonical_result.to_json_dict() if canonical_result.metrics else {}

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
    ) -> MetricsV1Result:
        """返回 V1 指标，以及指数、策略和超额收益序列。

        ``runtime_params`` 控制市场下跌、上涨阶段的判定阈值（7.1/7.2）。
        """
        from app.services.performance_analysis.facade import calculate_v1_metrics

        return calculate_v1_metrics(
            returns,
            runtime_params=runtime_params,
            analyzer=self,
        )
