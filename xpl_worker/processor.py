from __future__ import annotations

from typing import Any


def analyze_return_rows(return_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.services.xpl_service import xpl_analyzer

    return xpl_analyzer.get_return_analysis_v1(return_rows)

