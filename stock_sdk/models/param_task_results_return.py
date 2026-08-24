"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetParamTaskResultsReturnListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    task_id: str | None = None

@dataclass
class t_param_task_results_return(SerializableModel):
    id: int | None = None
    task_id: str | None = None
    stock_date: str | None = None
    index_return: float | None = None
    start_return: float | None = None
    returns_json: str | None = None

__all__ = ['GetParamTaskResultsReturnListRequestDto', 't_param_task_results_return']
