"""通用输入值解析工具。"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


def parse_int(value: Any, *, default: int | None = None) -> int | None:
    """解析整数；空值、布尔值和非法值返回 default。"""
    if value in (None, "") or isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number


def parse_float(value: Any, *, default: float | None = None) -> float | None:
    """解析有限浮点数；空值、布尔值和非法值返回 default。"""
    if value in (None, "") or isinstance(value, bool):
        return default
    try:
        number = float(str(value).strip().replace(",", "")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def parse_percent_like(value: Any, *, default: float | None = None) -> float | None:
    """解析数字或百分数字符串，``5%`` 转换为 ``0.05``。"""
    if value in (None, "") or isinstance(value, bool):
        return default
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text == "-":
        return default
    if text.endswith("%"):
        number = parse_float(text[:-1], default=default)
        return number / 100 if number is not None else default
    return parse_float(text, default=default)


def parse_ratio(value: Any, *, default: float | None = None) -> float | None:
    """解析比例，带百分号时转换为小数比例。"""
    return parse_percent_like(value, default=default)


def parse_date(value: Any, *, default: date | None = None) -> date | None:
    """解析 ISO 日期、datetime 或 date。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return default
