"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDataIndexListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    day: int | None = None
    name: str | None = None
    is_show: int | None = None

@dataclass
class t_stock_data_index(SerializableModel):
    id: int | None = None
    index_code: str | None = None
    index_name: str | None = None
    index_rate: float | None = None
    index_rate_price: float | None = None
    index_inflow: float | None = None
    index_date: str | None = None
    createtime: str | None = None
    index_open: float | None = None
    index_max: float | None = None
    index_min: float | None = None
    index_close: float | None = None
    index_close_y: float | None = None
    index_turnrate: float | None = None
    index_volume: float | None = None
    index_volume_price: float | None = None
    is_show: int | None = None

__all__ = ['GetDataIndexListRequestDto', 't_stock_data_index']
