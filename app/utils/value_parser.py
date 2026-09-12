"""通用输入值解析工具。"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any
from dateutil import parser
import numpy as np
import pandas as pd
import json

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


def coerce_bool(value: Any, default: bool = False) -> bool:
    """统一的布尔解析入口（utils 层单一实现，config_manager 附加哨兵语义）。

    兼容历史字符串与宽松写法（1/true/yes/on/t/y 等）；空串按既有约定视为
    False；无法识别的非空字符串返回 default。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('1', 'true', 'yes', 'on', 't', 'y'):
            return True
        if normalized in ('', '0', 'false', 'no', 'off', 'n'):
            return False
    return default


def parse_date(value: Any, *, default: date | None = None) -> date | None:
    """解析多种日期格式，支持 YYYY-MM-DD、YYYY/MM/DD、MM/DD/YYYY 等"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        # dateutil 可以解析绝大多数常见日期格式
        return parser.parse(text).date()
    except (ValueError, TypeError, OverflowError):
        return default



def _convert_pandas_to_native(obj, *, round_digits: int | None = None, non_finite_to_none: bool = False):
    """递归转换 Pandas 类型为 Python 原生类型。

    round_digits 非空时对浮点值统一保留小数位；non_finite_to_none 时将
    NaN/inf 等非有限浮点转换为 None（合法 JSON，语义为"无法计算"而非 0）。
    """

    def _normalize(value):
        if isinstance(value, float):
            if non_finite_to_none and not math.isfinite(value):
                return None
            if round_digits is not None:
                return round(value, round_digits)
        return value

    if isinstance(obj, pd.DataFrame):
        return [_convert_pandas_to_native(row, round_digits=round_digits, non_finite_to_none=non_finite_to_none) for row in obj.to_dict(orient='records')]
    elif isinstance(obj, pd.Series):
        return [_convert_pandas_to_native(item, round_digits=round_digits, non_finite_to_none=non_finite_to_none) for item in obj.tolist()]
    elif isinstance(obj, dict):
        return {k: _convert_pandas_to_native(v, round_digits=round_digits, non_finite_to_none=non_finite_to_none) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_pandas_to_native(item, round_digits=round_digits, non_finite_to_none=non_finite_to_none) for item in obj]
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat() if pd.notna(obj) else None
    elif isinstance(obj, pd.Timedelta):
        return str(obj) if pd.notna(obj) else None
    elif isinstance(obj, np.generic):
        return _normalize(obj.item())
    elif pd.isna(obj):
        return None
    else:
        return _normalize(obj)
