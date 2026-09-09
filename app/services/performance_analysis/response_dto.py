"""绩效分析计算结果的响应 DTO 定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class MetricsV1Result:
    """供接口、预览、报告和导出共同使用的 V1 统一结果。"""

    schema_version: str
    metrics: dict[str, Any]
    canonical_metrics: dict[str, Any]
    index_df: pd.DataFrame
    start_df: pd.DataFrame
    excess_df: pd.DataFrame

    def to_json_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的统一存储投影。

        用于 TaskResult 持久化：只保存 schema_version、完整指标和
        canonical 投影，日收益序列仍由 TaskResultReturn 单独存储，
        避免重复。
        """
        return {
            "schema_version": self.schema_version,
            "metrics": self.metrics,
            "canonical_metrics": self.canonical_metrics,
        }
