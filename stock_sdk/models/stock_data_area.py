"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetAreaListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    day: int | None = None
    name: str | None = None

@dataclass
class t_stock_data_area(SerializableModel):
    id: int | None = None
    area_name: str | None = None
    area_rate: float | None = None
    area_inflow: float | None = None
    area_inflow_maxbig: float | None = None
    area_inflow_big: float | None = None
    area_inflow_middle: float | None = None
    area_inflow_small: float | None = None
    area_inflow_stock_code: str | None = None
    area_inflow_stock_name: str | None = None
    area_date: str | None = None
    createtime: str | None = None
    area_rate_price: float | None = None
    area_open: float | None = None
    area_max: float | None = None
    area_min: float | None = None
    area_close: float | None = None
    area_close_y: float | None = None
    area_turnrate: float | None = None
    area_market_cap: float | None = None
    area_volume: float | None = None
    area_volume_price: float | None = None

__all__ = ['GetAreaListRequestDto', 't_stock_data_area']
