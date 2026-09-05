"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetEastMoneyStockQuoteRequestDto(SerializableModel):
    stock_code: str | None = None

@dataclass
class GetEastMoneyStockTrendsRequestDto(SerializableModel):
    secid: str | None = None

__all__ = ['GetEastMoneyStockQuoteRequestDto', 'GetEastMoneyStockTrendsRequestDto']
