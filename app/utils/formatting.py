"""文本与数值格式化共享工具（ponytail 审计 B8 收敛）。

此前 `_normalize_scientific_text`/`_max_yearly_repair_days`/`_strip_html_tags`/
`_parse_json` 在 report_query、multi_product、extractor、stock_search 等
服务中逐字复制，此处收敛为单一实现。
"""
from __future__ import annotations

from app.utils.json_utils import loads, JSONDecodeError
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.utils.value_parser import _convert_pandas_to_native

SCIENTIFIC_NOTATION_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+$")

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
_SERVER_TZ = datetime.now().astimezone().tzinfo


def to_beijing_iso(value: datetime | None) -> str | None:
    """把数据库中的服务器本地 naive 时间序列化为北京时间 ISO 字符串。

    生产容器时区为 UTC，直接 isoformat 会被前端当成浏览器本地时间显示，
    比北京时间早 8 小时。naive 值先按服务器本地时区解释，再统一转 Asia/Shanghai。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_SERVER_TZ)
    return value.astimezone(BEIJING_TZ).isoformat()


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
        return loads(raw) if raw else default
    except (TypeError, JSONDecodeError):
        return default


def sanitize_json_value(value: Any) -> Any:
    """递归转为严格 JSON 安全形态。

    全库唯一的 NaN/inf→None 清洗出口（收敛此前 base/backtest_api/
    text_analysis/backfill 四份拷贝）：dict / list,tuple,set / datetime→ISO /
    numpy·pandas 标量与帧 → 原生类型，叶子浮点经
    ``value_parser._convert_pandas_to_native(non_finite_to_none=True)`` 处理。
    """
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _convert_pandas_to_native(value, non_finite_to_none=True)
