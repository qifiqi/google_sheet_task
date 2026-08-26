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
    stock_code: str | None = None
    stock_name: str | None = None
    start_return_date: str | None = None
    end_return_date: str | None = None

@dataclass
class t_param_task_results_return(SerializableModel):
    id: int | None = None
    task_id: str | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    start_return_date: str | None = None
    end_return_date: str | None = None
    return_length: int | None = None
    stock_date: str | None = None
    index_return: str | None = None
    start_return: str | None = None

__all__ = ['GetParamTaskResultsReturnListRequestDto', 't_param_task_results_return']
