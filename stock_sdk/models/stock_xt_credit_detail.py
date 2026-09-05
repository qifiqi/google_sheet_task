"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class GetStockXtCreditDetailListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None

@dataclass
class t_stock_xt_credit_detail(SerializableModel):
    id: int | None = None
    account_type: int | None = None
    account_id: str | None = None
    m_nStatus: int | None = None
    m_nCalcConfig: int | None = None
    m_dFrozenCash: float | None = None
    m_dBalance: float | None = None
    m_dAvailable: float | None = None
    m_dPositionProfit: float | None = None
    m_dMarketValue: float | None = None
    m_dFetchBalance: float | None = None
    m_dStockValue: float | None = None
    m_dFundValue: float | None = None
    m_dTotalDebt: float | None = None
    m_dEnableBailBalance: float | None = None
    m_dPerAssurescaleValue: float | None = None
    m_dAssureAsset: float | None = None
    m_dFinDebt: float | None = None
    m_dFinDealAvl: float | None = None
    m_dFinFee: float | None = None
    m_dSloDebt: float | None = None
    m_dSloMarketValue: float | None = None
    m_dSloFee: float | None = None
    m_dOtherFare: float | None = None
    m_dFinMaxQuota: float | None = None
    m_dFinEnableQuota: float | None = None
    m_dFinUsedQuota: float | None = None
    m_dSloMaxQuota: float | None = None
    m_dSloEnableQuota: float | None = None
    m_dSloUsedQuota: float | None = None
    m_dSloSellBalance: float | None = None
    m_dUsedSloSellBalance: float | None = None
    m_dSurplusSloSellBalance: float | None = None
    createtime: str | None = None
    updatetime: str | None = None

__all__ = ['GetStockXtCreditDetailListRequestDto', 't_stock_xt_credit_detail']
