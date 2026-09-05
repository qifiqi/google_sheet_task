"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDataIndustryListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    day: int | None = None
    name: str | None = None

@dataclass
class t_stock_data_industry(SerializableModel):
    id: int | None = None
    industry_name: str | None = None
    industry_rate: float | None = None
    industry_inflow: float | None = None
    industry_inflow_maxbig: float | None = None
    industry_inflow_big: float | None = None
    industry_inflow_middle: float | None = None
    industry_inflow_small: float | None = None
    industry_inflow_stock_code: str | None = None
    industry_inflow_stock_name: str | None = None
    industry_date: str | None = None
    createtime: str | None = None
    industry_rate_price: float | None = None
    industry_open: float | None = None
    industry_max: float | None = None
    industry_min: float | None = None
    industry_close: float | None = None
    industry_close_y: float | None = None
    industry_turnrate: float | None = None
    industry_market_cap: float | None = None
    industry_volume: float | None = None
    industry_volume_price: float | None = None

__all__ = ['GetDataIndustryListRequestDto', 't_stock_data_industry']
