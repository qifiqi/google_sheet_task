"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetParamTaskLogsListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    task_id: str | None = None

@dataclass
class ParamTaskIdRequestDto(SerializableModel):
    task_id: str | None = None

@dataclass
class t_param_task_logs(SerializableModel):
    id: int | None = None
    task_id: str | None = None
    level: str | None = None
    message: str | None = None
    timestamp: str | None = None

__all__ = ['GetParamTaskLogsListRequestDto', 'ParamTaskIdRequestDto', 't_param_task_logs']
