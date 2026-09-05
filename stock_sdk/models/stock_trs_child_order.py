"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsChildOrderListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    order_date_begin: str | None = None
    order_date_end: str | None = None
    parent_id: int | None = None
    status: int | None = None

@dataclass
class t_stock_trs_child_orders(SerializableModel):
    id: int | None = None
    parent_id: int | None = None
    sequence_id: int | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_side: str | None = None
    entrust_id: str | None = None
    submittedtime: str | None = None
    limit_price: float | None = None
    target_qty: int | None = None
    filled_qty: int | None = None
    filled_notional: float | None = None
    status: int | None = None
    stock_remark: str | None = None
    createby: str | None = None
    createtime: str | None = None
    terminaltime: str | None = None
    userid: int | None = None
    account_id: str | None = None
    stock_exchange: str | None = None
    stock_offset: str | None = None
    entrust_type: str | None = None
    stock_deal_price: float | None = None
    cancelled_qty: float | None = None
    remaining_qty: float | None = None
    stock_dealid: str | None = None
    hedge_fund_account: str | None = None

__all__ = ['GetStockTrsChildOrderListRequestDto', 't_stock_trs_child_orders']
