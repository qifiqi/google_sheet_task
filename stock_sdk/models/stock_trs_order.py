"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsOrderListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    order_date_begin: str | None = None
    order_date_end: str | None = None
    status: int | None = None

@dataclass
class GetStockTrsOrderStatusRequestDto(SerializableModel):
    id: int | None = None
    status: int | None = None

@dataclass
class t_stock_trs_order(SerializableModel):
    id: int | None = None
    parent_no: str | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_side: str | None = None
    limit_price: float | None = None
    price_rule: int | None = None
    target_qty: int | None = None
    filled_qty: int | None = None
    filled_notional: float | None = None
    avg_fill_price: float | None = None
    participation_rate: float | None = None
    max_child_qty: int | None = None
    timeout_seconds: int | None = None
    status: int | None = None
    stock_remark: str | None = None
    createby: str | None = None
    createtime: str | None = None
    updatetime: str | None = None
    terminaltime: str | None = None
    userid: int | None = None

__all__ = ['GetStockTrsOrderListRequestDto', 'GetStockTrsOrderStatusRequestDto', 't_stock_trs_order']
