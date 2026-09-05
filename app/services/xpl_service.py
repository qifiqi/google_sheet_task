"""Backward-compatible imports for the legacy XPL service module."""

from app.services.performance_analysis_service import XPLAnalyzer, xpl_analyzer

__all__ = ["XPLAnalyzer", "xpl_analyzer"]
