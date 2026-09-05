"""绩效分析计算的请求 DTO 定义。

集中定义运行时可配置的计算参数，供调用方显式传入指标计算逻辑，
避免在计算组件中依赖 HTTP 请求或全局配置。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricsRuntimeParamsDTO:
    """市场阶段与极端单日指标的运行参数。"""

    market_downturn_threshold: float = -0.02
    market_upturn_threshold: float = 0.02
    # 7.3 极端单日表现：单日涨幅/跌幅判定阈值（对称使用）。
    daily_extreme_threshold: float = 0.02
    # 回撤发生次数/频率统计：单日跌幅阈值。
    daily_drawdown_threshold: float = 0.05

    @classmethod
    def from_raw(cls, raw: Any) -> "MetricsRuntimeParamsDTO":
        """把 HTTP 请求中的 runtime_params 解析并校验为运行参数。

        支持直接传入 DTO 实例、``None``（取默认值）或字段字典；
        数字允许以字符串形式传入（如 ``"-0.03"``）。
        """
        if raw is None:
            return cls()
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            raise ValueError("runtime_params 必须是对象")
        # slots=True 的 dataclass 字段默认值不能按类属性访问，这里用字面量保持一致。
        try:
            downturn = float(raw.get("market_downturn_threshold", -0.02))
            upturn = float(raw.get("market_upturn_threshold", 0.02))
            daily_extreme = float(raw.get("daily_extreme_threshold", 0.02))
            daily_drawdown = float(raw.get("daily_drawdown_threshold", 0.05))
        except (TypeError, ValueError) as exc:
            raise ValueError("市场阶段阈值必须是数字") from exc
        if not all(math.isfinite(value) for value in (downturn, upturn, daily_extreme, daily_drawdown)):
            raise ValueError("市场阶段阈值必须是有限数字")
        return cls(
            market_downturn_threshold=downturn,
            market_upturn_threshold=upturn,
            daily_extreme_threshold=daily_extreme,
            daily_drawdown_threshold=daily_drawdown,
        )
