"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockATargetCondListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None
    search_type: int | None = None
    first_vr: float | None = None
    last_vr: float | None = None
    stock_date_begin: str | None = None
    stock_date_end: str | None = None

@dataclass
class GetStockATargetCondSearchRequestDto(SerializableModel):
    stock_code: str | None = None
    stock_date: str | None = None

@dataclass
class t_stock_a_target_cond(SerializableModel):
    id: int | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_ths_industry: str | None = None
    stock_price: float | None = None
    first_vr: float | None = None
    last_vr: float | None = None
    is_alarm: int | None = None
    alarmtime: str | None = None
    search_type: int | None = None
    createtime: str | None = None
    stock_date: str | None = None
    updatetime: str | None = None

__all__ = ['GetStockATargetCondListRequestDto', 'GetStockATargetCondSearchRequestDto', 't_stock_a_target_cond']
