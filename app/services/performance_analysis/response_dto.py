"""性能分析结果 DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class MetricsV1ResponseDTO:
    """V1 完整计算结果，包含原始指标和三条派生收益序列。"""

    metrics: dict[str, Any]
    index_df: pd.DataFrame
    start_df: pd.DataFrame
    excess_df: pd.DataFrame
