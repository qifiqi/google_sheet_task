"""绩效分析域请求 Schema。

分析入参的深度校验由 performance_analysis_service 负责（含多态行格式），
body 边界仅约束为 JSON 对象。
"""

from typing import Any

from pydantic import RootModel


class PerformanceAnalysisPayloadSchema(RootModel[dict[str, Any]]):
    """POST /performance_analysis/analyze 与 /performance_analysis/v1/analyze 请求体。"""
