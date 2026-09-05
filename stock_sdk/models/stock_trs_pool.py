"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsPoolListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_keyword: str | None = None
    status: int | None = None

@dataclass
class t_stock_trs_pool(SerializableModel):
    id: int | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    east_code: str | None = None
    participation_rate: float | None = None
    max_child_qty: int | None = None
    timeout_seconds: int | None = None
    price_rule: int | None = None
    remark: str | None = None
    status: int | None = None
    createtime: str | None = None
    updatetime: str | None = None
    userid: int | None = None

__all__ = ['GetStockTrsPoolListRequestDto', 't_stock_trs_pool']
