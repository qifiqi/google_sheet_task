"""多产品收益组合的统一工具。

所有调用方都提供累计收益行（``date``、``index_return`` 和
``start_return``）。本模块集中管理比例和日期策略，避免预览、报告和导出
出现口径分叉。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import Any, Iterable


RATIO_BASE = Decimal("100")
DEFAULT_WEIGHTING_MODE = "daily_compound"
LEGACY_WEIGHTING_MODE = "legacy_cumulative"


def normalize_weight(value: Any) -> Decimal:
    """将 30、``30%`` 或 0.3 转换为小数形式的组合比例。"""
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError("产品比例不能为空")
    explicit_percent = text.endswith("%")
    raw = text[:-1].strip() if explicit_percent else text
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"产品比例不是有效数字: {value}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("产品比例必须是非负有限数")
    if explicit_percent or number > 1:
        number /= RATIO_BASE
    return number


def _coerce_bool(value: Any) -> bool:
    """Parse legacy boolean values without treating the string ``false`` as true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off", ""}:
        return False
    raise ValueError(f"无法解析组合 legacy 布尔值: {value}")


def normalize_weighting_mode(mode: Any = None, *, legacy: Any = False) -> str:
    """统一组合算法入口。

    旧版累计收益直接加权（legacy_cumulative）已停用，当前仅保留
    日收益加权后复利（daily_compound）一种算法。
    """
    # if mode in (None, ""):
    #     return LEGACY_WEIGHTING_MODE if _coerce_bool(legacy) else DEFAULT_WEIGHTING_MODE
    # normalized = str(mode).strip().lower()
    # if normalized in {DEFAULT_WEIGHTING_MODE, "daily", "compound"}:
    #     return DEFAULT_WEIGHTING_MODE
    # if normalized in {LEGACY_WEIGHTING_MODE, "legacy", "cumulative"}:
    #     return LEGACY_WEIGHTING_MODE
    # raise ValueError(f"不支持的组合 weighting_mode: {mode}")
    _ = mode, legacy
    return DEFAULT_WEIGHTING_MODE


def _valid_rows(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or row.get("stock_date") or "").strip()
        if not date:
            continue
        try:
            index_return = float(row["index_return"])
            start_return = float(row["start_return"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(index_return) or not math.isfinite(start_return):
            continue
        if index_return <= -1 or start_return <= -1:
            raise ValueError("累计收益率不能小于等于 -100%")
        normalized[date] = {"index_return": index_return, "start_return": start_return}
    return normalized


def cumulative_to_daily(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """将累计收益行转换为日收益行。"""
    row_map = _valid_rows(rows)
    previous_index_nav = Decimal("1")
    previous_start_nav = Decimal("1")
    result = []
    for date in sorted(row_map):
        current = row_map[date]
        index_nav = Decimal("1") + Decimal(str(current["index_return"]))
        start_nav = Decimal("1") + Decimal(str(current["start_return"]))
        if previous_index_nav == 0 or previous_start_nav == 0:
            raise ValueError("前一天净值为 0，无法计算当天收益率")
        result.append({
            "date": date,
            "index_return": float(index_nav / previous_index_nav - 1),
            "start_return": float(start_nav / previous_start_nav - 1),
        })
        previous_index_nav = index_nav
        previous_start_nav = start_nav
    return result


def daily_to_cumulative(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """将日收益行复利还原为累计收益行。"""
    row_map = _valid_rows(rows)
    index_nav = Decimal("1")
    start_nav = Decimal("1")
    result = []
    for date in sorted(row_map):
        current = row_map[date]
        index_nav *= Decimal("1") + Decimal(str(current["index_return"]))
        start_nav *= Decimal("1") + Decimal(str(current["start_return"]))
        result.append({
            "date": date,
            "index_return": float(index_nav - 1),
            "start_return": float(start_nav - 1),
        })
    return result


def combine_product_returns(
    products: Iterable[dict[str, Any]],
    *,
    weights: Iterable[Any] | None = None,
    weighting_mode: Any = None,
    legacy: Any = False,
    common_date_policy: str = "intersection",
) -> list[dict[str, Any]]:
    """使用统一算法组合各产品的累计收益。

    ``products`` 可以包含 ``returns``/``return_date``，并可选提供
    ``ratio``/``weight``。组合只使用所有产品都存在的共同日期。
    """
    product_list = list(products or [])
    if not product_list:
        return []
    if common_date_policy != "intersection":
        raise ValueError(f"不支持的共同日期策略: {common_date_policy}")
    raw_weights = list(weights) if weights is not None else [
        item.get("weight", item.get("ratio")) for item in product_list
    ]
    if len(raw_weights) != len(product_list):
        raise ValueError("比例数量与产品数量不一致")
    normalized_weights = [normalize_weight(value) for value in raw_weights]
    # 旧版累计收益直接加权算法已停用，仅保留日收益加权后复利。
    # mode = normalize_weighting_mode(weighting_mode, legacy=legacy)
    mode = DEFAULT_WEIGHTING_MODE

    product_maps: list[dict[str, dict[str, float]]] = []
    common_dates: set[str] | None = None
    for product in product_list:
        rows = product.get("returns", product.get("return_date", [])) if isinstance(product, dict) else []
        row_map = _valid_rows(rows)
        if not row_map:
            return []
        dates = set(row_map)
        common_dates = dates if common_dates is None else common_dates & dates
        product_maps.append(row_map)
    if not common_dates:
        return []

    ordered_dates = sorted(common_dates)
    # if mode == DEFAULT_WEIGHTING_MODE:
    # 先截取共同日期，再从共同区间的初始净值 1.0 还原日收益，
    # 避免共同区间首日错误引用产品在区间外的前一日数据。
    daily_maps = []
    for row_map in product_maps:
        common_rows = [
            {"date": date, **row_map[date]}
            for date in ordered_dates
        ]
        daily_maps.append(_valid_rows(cumulative_to_daily(common_rows)))
    # else:
    #     daily_maps = [
    #         {date: row_map[date] for date in ordered_dates}
    #         for row_map in product_maps
    #     ]

    weighted_rows = []
    for date in ordered_dates:
        index_total = sum(
            Decimal(str(row_map[date]["index_return"])) * weight
            for row_map, weight in zip(daily_maps, normalized_weights)
        )
        start_total = sum(
            Decimal(str(row_map[date]["start_return"])) * weight
            for row_map, weight in zip(daily_maps, normalized_weights)
        )
        weighted_rows.append({
            "date": date,
            "index_return": float(index_total),
            "start_return": float(start_total),
        })
    # return weighted_rows if mode == LEGACY_WEIGHTING_MODE else daily_to_cumulative(weighted_rows)
    return daily_to_cumulative(weighted_rows)
