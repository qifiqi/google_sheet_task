"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockCnOrderListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    username: str | None = None
    stock_date: str | None = None
    stock_name: str | None = None

@dataclass
class t_stock_cn_order(SerializableModel):
    id: int | None = None
    username: str | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    stock_price: float | None = None
    stock_quantity: int | None = None
    stock_position: int | None = None
    stock_direction: str | None = None
    stock_date: str | None = None
    createtime: str | None = None
    order_no: str | None = None
    stock_account: str | None = None

__all__ = ['GetStockCnOrderListRequestDto', 't_stock_cn_order']
