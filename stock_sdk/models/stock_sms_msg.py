"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class t_stock_smsmsg(SerializableModel):
    id: int | None = None
    sms_content: str | None = None
    sms_phone: str | None = None
    sms_time: str | None = None

__all__ = ['t_stock_smsmsg']
