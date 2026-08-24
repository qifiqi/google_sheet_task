"""Persistence helpers for task return series."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def build_return_series_fields(
    return_rows: Iterable[dict[str, Any]] | None,
    *,
    stock_code: Any,
    stock_name: Any,
) -> dict[str, Any] | None:
    rows = [row for row in (return_rows or []) if isinstance(row, dict)]
    if not rows:
        return None
    dates = [row.get("stock_date") or row.get("date") for row in rows]
    index_returns = [row.get("index_return") for row in rows]
    start_returns = [row.get("start_return") for row in rows]
    parsed_dates = [_as_date(value) for value in dates]
    valid_dates = [value for value in parsed_dates if value is not None]
    if not valid_dates:
        return None
    return {
        "stock_code": str(stock_code or "").strip() or "UNKNOWN",
        "stock_name": str(stock_name or stock_code or "未知股票").strip() or "未知股票",
        "start_return_date": min(valid_dates),
        "end_return_date": max(valid_dates),
        "return_length": len(rows),
        "stock_date": json.dumps(dates, ensure_ascii=False, allow_nan=False),
        "index_return": json.dumps(index_returns, ensure_ascii=False, allow_nan=False),
        "start_return": json.dumps(start_returns, ensure_ascii=False, allow_nan=False),
    }


def parse_return_series_fields(series: Any) -> list[dict[str, Any]]:
    """Read the split return-series columns."""
    def load(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value) if value else []
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []

    dates = load(getattr(series, "stock_date", None))
    index_returns = load(getattr(series, "index_return", None))
    start_returns = load(getattr(series, "start_return", None))
    if dates:
        return [
            {
                "date": value,
                "index_return": index_returns[index] if index < len(index_returns) else None,
                "start_return": start_returns[index] if index < len(start_returns) else None,
            }
            for index, value in enumerate(dates)
        ]

    return []


def extract_return_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("_return_date", "return_date"):
            rows = value.get(key)
            if isinstance(rows, list):
                return rows
        for child in value.values():
            rows = extract_return_rows(child)
            if rows:
                return rows
    elif isinstance(value, list):
        for child in value:
            rows = extract_return_rows(child)
            if rows:
                return rows
    return []
