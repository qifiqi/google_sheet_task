"""K 线序列准备公共件（C 系列 C4~C7 共享的流水线步骤，2026-09 审计 C2）。

抽取各任务 service 中重复的"原始K线校验"与"过滤 → 投影 → 写入Sheet校验"
两段；各任务的差异（limit 系数、取数入口、起始日期钳制、full_years 边界、
stock 元数据同步、中段区间 raise 时序）仍留在各自 service 中，不强行抽象。
"""

from __future__ import annotations

from typing import Any

from app.utils.kline_validation import require_kline_rows


def project_and_validate_write_ready(
    kline_service,
    *,
    parameter: str,
    market_type: str,
    klines: list[dict[str, Any]],
    price_mode: str | None,
    price_field: str | None = None,
    start_date: str,
    end_date: str,
    data_end_date: str,
    include_ohlc: bool = False,
) -> list[dict[str, Any]]:
    """区间过滤 → build_price_rows 投影 → 写入Sheet K线校验。

    kline_service：KlineService 实例（投影统一走 build_price_rows）；
    price_mode/price_field 二选一：显式字段（如 C4 按市场取价）优先，
    否则按 price_mode 走统一映射；include_ohlc 为 C7 的 OHLC 四价模式。
    """
    klines = [
        kline for kline in klines
        if start_date <= kline["stock_date"] <= end_date
    ]
    all_kline = kline_service.build_price_rows(
        klines, price_mode, start_date=start_date, end_date=end_date,
        price_field=price_field, include_ohlc=include_ohlc,
    )
    return require_kline_rows(
        parameter,
        market_type,
        all_kline,
        context="写入Sheet K线",
        start_date=start_date,
        end_date=end_date,
        latest_date=data_end_date,
    )
