"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockFinancialDataRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_concept: str | None = None
    stock_industry: str | None = None
    stock_area: str | None = None
    stock_is_up: int | None = None
    stock_code: str | None = None

@dataclass
class t_stock_financial_data(SerializableModel):
    id: int | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    stock_financial_date: str | None = None
    stock_financial_push_date: str | None = None
    stock_push_7change: str | None = None
    stock_push_15change: str | None = None
    stock_concept: str | None = None
    stock_industry: str | None = None
    stock_area: str | None = None
    stock_growth: float | None = None
    stock_is_up: int | None = None
    createtime: str | None = None

__all__ = ['GetStockFinancialDataRequestDto', 't_stock_financial_data']
