"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

class ModelTypeEnum(IntEnum):
    VALUE_0 = 0
    VALUE_1 = 1
    VALUE_2 = 2

@dataclass
class ResponseDto(SerializableModel):
    ret_code: int | None = None
    ret_msg: str | None = None
    ret_count: int | None = None
    ret_obj: Any | None = None

class UserStatusEnum(IntEnum):
    VALUE_0 = 0
    VALUE_1 = 1

__all__ = ['ModelTypeEnum', 'ResponseDto', 'UserStatusEnum']
