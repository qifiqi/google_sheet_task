"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDataByPageListForWindowsRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None

@dataclass
class GetStockXtOrderListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    userid: int | None = None
    stock_code: str | None = None

@dataclass
class t_stock_xt_order(SerializableModel):
    id: int | None = None
    account_type: int | None = None
    order_id: int | None = None
    account_id: str | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    order_sysid: str | None = None
    order_time: str | None = None
    order_type: int | None = None
    order_volume: int | None = None
    stock_price: float | None = None
    traded_volume: int | None = None
    traded_price: float | None = None
    order_status: int | None = None
    status_msg: str | None = None
    strategy_name: str | None = None
    order_remark: str | None = None
    direction: int | None = None
    offset_flag: int | None = None
    createtime: str | None = None

__all__ = ['GetDataByPageListForWindowsRequestDto', 'GetStockXtOrderListRequestDto', 't_stock_xt_order']
