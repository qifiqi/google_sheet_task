from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.exceptions.checkForErrors import checkForErrors
from app.utils.result_validator import is_valid_result_value


def parse_result_value(position: str, value: Any, *, allow_dash: bool = False) -> Any:
    """将单个表格结果值转换为可计算的数值。"""
    if not value or not is_valid_result_value(value):
        raise ValueError(f"结果位置 {position} 值为空或无效")

    stripped = str(value).strip()
    if stripped.startswith(("#", "#N/A")):
        raise checkForErrors(f"检查报错，出现 # 或 #N/A 异常，请联系用户排查: {position}={value}")

    if allow_dash and stripped == "-":
        return None

    if "%" in stripped:
        return float(stripped.replace("%", "").replace(",", "")) / 100

    if isinstance(value, str):
        return float(stripped.replace(",", ""))

    return value


def parse_result_mapping(result_values: Dict[str, Any], *, allow_dash: bool = False) -> Dict[str, Any]:
    """批量解析结果区域的值。"""
    parsed_values: Dict[str, Any] = {}
    for position, value in result_values.items():
        parsed_value = parse_result_value(position, value, allow_dash=allow_dash)
        if allow_dash and parsed_value is None:
            continue
        parsed_values[position] = parsed_value
    return parsed_values


def is_result_range_changed(
    initial_values: Dict[str, Any],
    current_values: Dict[str, Any],
    compare_keys: Iterable[str],
) -> bool:
    """检查结果区关键单元格是否已经发生变化。"""
    for key in compare_keys:
        if initial_values.get(key) != current_values.get(key):
            return True
    return False


def has_invalid_result_markers(result_values: Dict[str, Any]) -> bool:
    """检查结果区是否还存在明显无效值。"""
    if not result_values:
        return True

    for value in result_values.values():
        if not value or value in ["#DIV/0!", "", "#N/A", "#ERROR!", "#VALUE!"]:
            return True
        if "target" in str(value).lower():
            return True
    return False


def build_stock_value_series(
    kline: List[Dict[str, Any]],
    result_values: Dict[str, Any],
    column_name: str,
) -> List[Dict[str, Any]]:
    """根据结果列值构造收益曲线序列。"""
    series = []
    for index, item in enumerate(kline):
        series.append(
            {
                "stock_date": item.get("stock_date"),
                "stock_val": result_values[f"{column_name}{index + 2}"],
            }
        )
    return series
