"""回测收益与绩效分析的内部组件包。

该包按数据来源、指标计算、结果适配和导出职责拆分；由上层
``PerformanceAnalysisService`` 组合各 MixIn 对外提供统一能力。
"""

from .facade import calculate_v1_metrics
from .portfolio_combiner import combine_product_returns, normalize_weight

__all__ = ["calculate_v1_metrics", "combine_product_returns", "normalize_weight"]
