"""文本与数值格式化共享工具（ponytail 审计 B8 收敛）。

此前 `_normalize_scientific_text`/`_max_yearly_repair_days`/`_strip_html_tags`/
`_parse_json` 在 report_query、multi_product、extractor、stock_search 等
服务中逐字复制，此处收敛为单一实现。
"""
from __future__ import annotations

import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

SCIENTIFIC_NOTATION_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+$")


def normalize_scientific_text(text: str) -> str:
    """科学计数法文本转普通十进制写法；非科学计数法/非有限值原样返回。"""
    if not SCIENTIFIC_NOTATION_RE.fullmatch(text):
        return text

    try:
        number = Decimal(text)
    except InvalidOperation:
        return text

    if not number.is_finite():
        return text

    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", "+0"} else normalized


def max_yearly_repair_days(yearly_repair_days: Any) -> float | None:
    """返回年度修复天数字典中的最大有限数值；空/无有效值返回 None。"""
    if not isinstance(yearly_repair_days, dict):
        return None
    values = [
        value for value in yearly_repair_days.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value)
    ]
    return max(values) if values else None


def strip_html_tags(value: Any) -> str:
    """去除文本中的 HTML 标签并去除首尾空白。"""
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def parse_lenient_json(raw: Any, default: Any) -> Any:
    """宽容 JSON 解析：已是 dict/list 原样返回，解析失败返回 default。"""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default
