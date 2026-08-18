"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockMinuteTickListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None
    time_begin: str | None = None
    time_end: str | None = None

@dataclass
class LongIdRequestDto(SerializableModel):
    id: int | None = None

@dataclass
class t_stock_minute_tick(SerializableModel):
    id: int | None = None
    time: str | None = None
    open: float | None = None
    close: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    amount: float | None = None
    avg: float | None = None
    stock_code: str | None = None
    create_time: str | None = None

__all__ = ['GetStockMinuteTickListRequestDto', 'LongIdRequestDto', 't_stock_minute_tick']
