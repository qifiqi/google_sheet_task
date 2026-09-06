"""XPL 分析域请求 Schema。

分析入参的深度校验由 xpl_analysis_service 负责（含多态行格式），
body 边界仅约束为 JSON 对象。
"""

from typing import Any

from pydantic import RootModel


class AnalyzePayloadSchema(RootModel[dict[str, Any]]):
    """POST /xpl/analyze 与 /xpl/v1/analyze 请求体。"""
