"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTop10CirculatingListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None

@dataclass
class t_stock_top10_circulating(SerializableModel):
    id: int | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    stock_sum_count: int | None = None
    stock_add_count: int | None = None
    createtime: str | None = None
    updatetime: str | None = None

__all__ = ['GetStockTop10CirculatingListRequestDto', 't_stock_top10_circulating']
