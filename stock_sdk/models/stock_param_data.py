"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockParamDataListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    tempate_name: str | None = None
    task_no: str | None = None

@dataclass
class t_stock_param_data(SerializableModel):
    id: int | None = None
    task_no: str | None = None
    stock_index: int | None = None
    template_id: int | None = None
    stock_no: str | None = None
    multiplier: float | None = None
    danbian: float | None = None
    xiancang: float | None = None
    zhishu: float | None = None
    smoothing: float | None = None
    bordering: float | None = None
    createtime: str | None = None
    return_rate: float | None = None
    annualized_rate: float | None = None
    maxdd: float | None = None
    index_rate: float | None = None
    index_annualized_rate: float | None = None
    max_index_dd: float | None = None
    fee_total: float | None = None
    fee_annualized: float | None = None
    year_rate: float | None = None

__all__ = ['GetStockParamDataListRequestDto', 't_stock_param_data']
