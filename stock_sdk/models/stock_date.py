"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class t_stock_date(SerializableModel):
    id: int | None = None
    stock_date: str | None = None

__all__ = ['t_stock_date']
