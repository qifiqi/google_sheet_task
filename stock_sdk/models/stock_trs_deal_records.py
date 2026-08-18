"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsDealRecordsListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None
    stock_side: str | None = None
    terminaltime_begin: str | None = None
    terminaltime_end: str | None = None

@dataclass
class t_stock_trs_deal_records(SerializableModel):
    id: int | None = None
    account_id: str | None = None
    stock_code: str | None = None
    stock_exchange: str | None = None
    entrust_id: str | None = None
    deal_id: int | None = None
    terminaltime: str | None = None
    stock_side: str | None = None
    stock_offset: str | None = None
    filled_qty: int | None = None
    stock_deal_price: float | None = None
    filled_notional: float | None = None
    hedge_fund_account: str | None = None
    target_qty: int | None = None
    status: int | None = None
    remaining_qty: int | None = None

__all__ = ['GetStockTrsDealRecordsListRequestDto', 't_stock_trs_deal_records']
