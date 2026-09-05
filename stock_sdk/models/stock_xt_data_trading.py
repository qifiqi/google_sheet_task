"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockXtDataTradingListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    userid: int | None = None
    stock_code: str | None = None

@dataclass
class t_stock_xt_data_trading(SerializableModel):
    id: int | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    stock_type: int | None = None
    stock_price: float | None = None
    traded_volume: int | None = None
    userid: int | None = None
    createtime: str | None = None
    updatetime: str | None = None
    state: int | None = None
    order_id: int | None = None

__all__ = ['GetStockXtDataTradingListRequestDto', 't_stock_xt_data_trading']
