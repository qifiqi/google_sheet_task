"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockParamTuningListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_name: str | None = None

@dataclass
class t_stock_param_tuning(SerializableModel):
    id: int | None = None
    stock_no: str | None = None
    stock_name: str | None = None
    template_id: int | None = None
    tun_state: int | None = None
    createby: str | None = None
    userid: int | None = None
    createtime: str | None = None

__all__ = ['GetStockParamTuningListRequestDto', 't_stock_param_tuning']
