"""绩效分析计算结果的响应 DTO 定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class MetricsV1ResponseDTO:
    """V1 完整计算结果，包含标准化指标和三条派生收益序列。"""

    metrics: dict[str, Any]
    index_df: pd.DataFrame
    start_df: pd.DataFrame
    excess_df: pd.DataFrame
    canonical_metrics: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MetricsV1Result:
    """供接口、预览、报告和导出共同使用的 V1 统一结果。"""

    schema_version: str
    metrics: dict[str, Any]
    canonical_metrics: dict[str, Any]
    index_df: pd.DataFrame
    start_df: pd.DataFrame
    excess_df: pd.DataFrame

    def to_json_dict(self, *, include_series: bool = False) -> dict[str, Any]:
        """返回 JSON 安全的统一存储/传输投影。

        ``include_series=False``（默认）用于 TaskResult 持久化：只保存
        schema_version、完整指标和 canonical 投影，日收益序列仍由
        TaskResultReturn 单独存储，避免重复。
        """
        payload = {
            "schema_version": self.schema_version,
            "metrics": self.metrics,
            "canonical_metrics": self.canonical_metrics,
        }
        if not include_series:
            return payload

        def frame_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
            if frame is None or frame.empty:
                return []
            rows = frame.copy()
            if "date" in rows.columns:
                rows["date"] = rows["date"].map(
                    lambda value: value.isoformat() if hasattr(value, "isoformat") else value
                )
            return rows.to_dict(orient="records")

        payload["series"] = {
            "benchmark": frame_rows(self.index_df),
            "strategy": frame_rows(self.start_df),
            "excess": frame_rows(self.excess_df),
        }
        return payload
