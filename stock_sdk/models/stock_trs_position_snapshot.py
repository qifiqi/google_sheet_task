"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsPositionSnapshottRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    order_date_begin: str | None = None
    order_date_end: str | None = None
    stock_code: str | None = None

@dataclass
class t_stock_trs_position_snapshot(SerializableModel):
    id: int | None = None
    account_id: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    bsflag: str | None = None
    current_quantity: int | None = None
    available_quantity: int | None = None
    cost_price: float | None = None
    yd_quantity: int | None = None
    td_quantity: int | None = None
    long_frozen: int | None = None
    short_frozen: int | None = None
    position_profit: float | None = None
    close_profit: float | None = None
    commission: float | None = None
    margin: float | None = None
    hedge: str | None = None
    frozen_quantity: int | None = None
    currency: str | None = None
    userid: int | None = None
    createtime: str | None = None

__all__ = ['GetStockTrsPositionSnapshottRequestDto', 't_stock_trs_position_snapshot']
