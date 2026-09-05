"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class t_stock_trs_account(SerializableModel):
    id: int | None = None
    account: str | None = None
    account_state: int | None = None
    account_id: str | None = None
    currency: str | None = None
    total_assets: float | None = None
    market_value: float | None = None
    available_funds: float | None = None
    withdrawable_funds: float | None = None
    frozen_funds: float | None = None
    balance: float | None = None
    equity: float | None = None
    pre_equity: float | None = None
    position_profit: float | None = None
    close_profit: float | None = None
    current_margin: float | None = None
    available_margin: float | None = None
    long_available_funds: float | None = None
    short_available_funds: float | None = None
    risk: float | None = None
    userid: int | None = None
    createtime: str | None = None

__all__ = ['t_stock_trs_account']
