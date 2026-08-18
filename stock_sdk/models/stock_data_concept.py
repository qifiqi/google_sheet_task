"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDataConceptListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    day: int | None = None
    name: str | None = None

@dataclass
class t_stock_data_concept(SerializableModel):
    id: int | None = None
    concept_name: str | None = None
    concept_rate: float | None = None
    concept_inflow: float | None = None
    concept_inflow_maxbig: float | None = None
    concept_inflow_big: float | None = None
    concept_inflow_middle: float | None = None
    concept_inflow_small: float | None = None
    concept_inflow_stock_code: str | None = None
    concept_inflow_stock_name: str | None = None
    concept_date: str | None = None
    createtime: str | None = None
    concept_rate_price: float | None = None
    concept_open: float | None = None
    concept_max: float | None = None
    concept_min: float | None = None
    concept_close: float | None = None
    concept_close_y: float | None = None
    concept_turnrate: float | None = None
    concept_market_cap: float | None = None
    concept_volume: float | None = None
    concept_volume_price: float | None = None

__all__ = ['GetDataConceptListRequestDto', 't_stock_data_concept']
