"""单品回测参数行规范化工具。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


DEFAULT_C3_COMMISSION = "0.0350%"
C3_PARAMETER_KEYS = ("xm", "dbbh1", "dbbh2", "zlxc", "zsgz", "ywf1", "ywf2")


def derive_dbbh2(dbbh1: Any) -> str:
    """根据单边保护 1 推导单边保护 2。"""
    text = _clean_cell(dbbh1).replace(",", "")
    if not text:
        return ""
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return ""

    derived = Decimal("2") - value
    normalized = derived.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").rstrip("0").rstrip(".")


def normalize_backtest_training_config(config: dict[str, Any]) -> dict[str, Any]:
    """规范化 C3 回测参数，同时保持 C5 风格行数据不变。"""
    if not isinstance(config, dict) or not _is_c3_config(config):
        return config

    parameters = config.get("parameters")
    if not isinstance(parameters, list):
        return config

    normalized = dict(config)
    normalized["parameters"] = [
        normalize_c3_parameter_row(row)
        for row in parameters
    ]
    return normalized


def normalize_c3_parameter_dict(row: dict[str, Any]) -> dict[str, str]:
    """将按字段名组织的导入 C3 参数对象转换为标准参数行。"""
    normalized = {
        key: _clean_cell(row.get(key))
        for key in C3_PARAMETER_KEYS
    }
    if not normalized["dbbh2"] and normalized["dbbh1"]:
        normalized["dbbh2"] = derive_dbbh2(normalized["dbbh1"])
    return normalized


def normalize_c3_parameter_row(row: Any) -> Any:
    """将粘贴或 API 传入的 C3 行数据规范为标准参数顺序。"""
    if isinstance(row, dict):
        normalized = normalize_c3_parameter_dict(row)
        commission = _clean_cell(row.get("commission")) or DEFAULT_C3_COMMISSION
        return [commission, *[normalized[key] for key in C3_PARAMETER_KEYS]]
    if not isinstance(row, (list, tuple)):
        return row

    cells = [_clean_cell(value) for value in row]
    trimmed = _trim_trailing_empty(cells)

    if len(trimmed) == 2:
        return trimmed
    if len(trimmed) == 8:
        return trimmed
    if len(trimmed) == 7 and _is_commission_cell(trimmed[0]):
        return [trimmed[0], *_expand_six_value_business_row(trimmed[1:])]
    if len(trimmed) == 7:
        return [DEFAULT_C3_COMMISSION, *trimmed]
    if len(trimmed) == 6:
        return [DEFAULT_C3_COMMISSION, *_expand_six_value_business_row(trimmed)]

    return trimmed


def _expand_six_value_business_row(values: list[str]) -> list[str]:
    """将缺少派生字段的六列 C3 业务参数扩展为标准七列。"""
    return [
        values[0],
        values[1],
        derive_dbbh2(values[1]),
        values[2],
        values[3],
        values[4],
        values[5],
    ]


def _is_c3_config(config: dict[str, Any]) -> bool:
    """判断配置是否属于需要规范化参数行的 C3 单品回测。"""
    model_version = str(config.get("model_version") or "").strip().lower()
    if model_version in {"c4", "c5"}:
        return False

    sheet = config.get("sheet") if isinstance(config.get("sheet"), dict) else {}
    title_parts = [
        config.get("sheet_name"),
        sheet.get("sheet_name"),
        sheet.get("title"),
    ]
    title = " ".join(str(value or "") for value in title_parts).upper()
    return "C4" not in title and "C5" not in title


def _is_commission_cell(value: Any) -> bool:
    """判断单元格文本是否可识别为佣金字段。"""
    normalized = _clean_cell(value).lower()
    return "%" in normalized or normalized in {"commission", "手续费"}


def _clean_cell(value: Any) -> str:
    """清理 Excel 单元格值为去除空白的普通文本。"""
    return "" if value is None else str(value).strip()


def _trim_trailing_empty(values: list[str]) -> list[str]:
    """移除参数行尾部多余的空单元格。"""
    trimmed = list(values)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed
