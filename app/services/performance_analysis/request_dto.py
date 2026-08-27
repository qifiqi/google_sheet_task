"""性能分析请求参数 DTO。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricsRuntimeParamsDTO:
    """市场阶段指标的运行参数。"""

    market_downturn_threshold: float = -0.02
    market_upturn_threshold: float = 0.02
