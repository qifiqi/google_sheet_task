"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDataStateListRequestDto(SerializableModel):
    pass

@dataclass
class GetStockXtDataListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    userid: int | None = None
    stock_code: str | None = None
    state: int | None = None

@dataclass
class UpdateStateRequestDto(SerializableModel):
    id: int | None = None
    state: int | None = None

@dataclass
class UpdateUserRequestDto(SerializableModel):
    id: int | None = None
    userid: int | None = None

@dataclass
class t_stock_xt_data(SerializableModel):
    id: int | None = None
    stock_name: str | None = None
    stock_code: str | None = None
    state: int | None = None
    userid: int | None = None
    updatetime: str | None = None
    createtime: str | None = None

__all__ = ['GetDataStateListRequestDto', 'GetStockXtDataListRequestDto', 'UpdateStateRequestDto', 'UpdateUserRequestDto', 't_stock_xt_data']
