"""绩效分析计算的请求 DTO 定义。

集中定义运行时可配置的计算参数，供调用方显式传入指标计算逻辑，
避免在计算组件中依赖 HTTP 请求或全局配置。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricsRuntimeParamsDTO:
    """市场阶段指标的运行参数。"""

    market_downturn_threshold: float = -0.02
    market_upturn_threshold: float = 0.02
