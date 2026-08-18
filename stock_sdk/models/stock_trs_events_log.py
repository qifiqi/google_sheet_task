"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockTrsEventsLogListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    event_type: str | None = None
    log_date_begin: str | None = None
    log_date_end: str | None = None

@dataclass
class t_stock_trs_events_log(SerializableModel):
    id: int | None = None
    parent_id: int | None = None
    child_id: int | None = None
    event_type: str | None = None
    stock_remark: str | None = None
    createtime: str | None = None
    userid: int | None = None

__all__ = ['GetStockTrsEventsLogListRequestDto', 't_stock_trs_events_log']
