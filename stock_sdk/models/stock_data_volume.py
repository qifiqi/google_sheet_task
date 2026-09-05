"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockDataVolumeHisListRequestDto(SerializableModel):
    stock_date: str | None = None

@dataclass
class GetStockDataVolumeListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None
    min_coefficient: float | None = None
    max_coefficient: float | None = None
    stock_concept: str | None = None
    stock_lelvel: int | None = None

@dataclass
class GetStockDataVolumeRequestDto(SerializableModel):
    day_max_volume: int | None = None
    max_volume_coefficient: float | None = None
    where_max_count: str | None = None
    day_current_volume: int | None = None
    coefficient: float | None = None
    his_day_max_volume: int | None = None
    stock_concept: str | None = None
    stock_lelvel: int | None = None

@dataclass
class t_stock_data_volume(SerializableModel):
    id: int | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_max_volume: int | None = None
    stock_day_volume: int | None = None
    createtime: str | None = None
    updatetime: str | None = None
    stock_avg_price: float | None = None
    stock_avg_price_90: float | None = None
    stock_avg_price_70: float | None = None
    stock_concept: str | None = None
    stock_industry: str | None = None
    stock_lelvel: int | None = None
    double_time: str | None = None
    stock_macd_day_date: str | None = None
    stock_macd_month_date: str | None = None
    stock_limit_count: int | None = None
    stock_inflow: float | None = None

@dataclass
class t_stock_data_volume_his(SerializableModel):
    id: int | None = None
    stock_date: str | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_max_volume: int | None = None
    stock_day_volume: int | None = None
    createtime: str | None = None
    stock_avg_price: float | None = None
    stock_avg_price_90: float | None = None
    stock_avg_price_70: float | None = None
    stock_lelvel: int | None = None
    stock_macd_day_date: str | None = None
    stock_macd_month_date: str | None = None
    stock_limit_count: int | None = None
    stock_inflow: float | None = None

__all__ = ['GetStockDataVolumeHisListRequestDto', 'GetStockDataVolumeListRequestDto', 'GetStockDataVolumeRequestDto', 't_stock_data_volume', 't_stock_data_volume_his']
