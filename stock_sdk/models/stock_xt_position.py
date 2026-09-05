"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockXtPositionListForWindowsRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None

@dataclass
class GetStockXtPositionListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    userid: int | None = None
    stock_code: str | None = None

@dataclass
class t_stock_xt_position(SerializableModel):
    id: int | None = None
    account_type: int | None = None
    account_id: str | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    volume: int | None = None
    can_use_volume: int | None = None
    frozen_volume: int | None = None
    on_road_volume: int | None = None
    yesterday_volume: int | None = None
    open_price: float | None = None
    market_value: float | None = None
    avg_price: float | None = None
    direction: int | None = None
    createtime: str | None = None
    updatetime: str | None = None

__all__ = ['GetStockXtPositionListForWindowsRequestDto', 'GetStockXtPositionListRequestDto', 't_stock_xt_position']
