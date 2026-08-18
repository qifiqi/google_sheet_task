"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetDicListForSelectRequestDto(SerializableModel):
    dic_key: str | None = None

__all__ = ['GetDicListForSelectRequestDto']
