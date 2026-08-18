"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockParamTemplateListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    tempate_name: str | None = None

@dataclass
class t_stock_param_template(SerializableModel):
    id: int | None = None
    tempate_name: str | None = None
    param_method: int | None = None
    model_ver: str | None = None
    param_value: str | None = None
    createtime: str | None = None
    createby: str | None = None
    userid: int | None = None

__all__ = ['GetStockParamTemplateListRequestDto', 't_stock_param_template']
