"""Generated request and entity models. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ..model_base import SerializableModel

@dataclass
class DeleteStockParamResultRequestDto(SerializableModel):
    task_index: int | None = None
    task_id: str | None = None

@dataclass
class GetSingleStockTemplateRequestDto(SerializableModel):
    stock_code: str | None = None

@dataclass
class GetStockParamResultListRequestDto(SerializableModel):
    page_index: int | None = None
    page_size: int | None = None
    order_field: str | None = None
    order_type: str | None = None
    stock_code: str | None = None
    task_id: str | None = None
    task_index: int | None = None

@dataclass
class t_stock_param_result(SerializableModel):
    id: int | None = None
    task_id: str | None = None
    stock_code: str | None = None
    multiplier: float | None = None
    danbian: float | None = None
    xiancang: float | None = None
    zhishu: float | None = None
    smoothing: float | None = None
    bordering: float | None = None
    ml: str | None = None
    task_index: int | None = None
    kline_range: str | None = None
    return_rate: float | None = None
    annualized_rate: float | None = None
    maxdd: float | None = None
    index_rate: float | None = None
    index_annualized_rate: float | None = None
    max_index_dd: float | None = None
    fee_total: float | None = None
    fee_annualized: float | None = None
    year_rate: float | None = None
    turnover_rate: float | None = None
    return_beats: float | None = None
    dd_beats: float | None = None
    max_1y_beats: float | None = None
    min_1y_beats: float | None = None
    max_theoretical_leverage: float | None = None
    avg_theoretical_leverage: float | None = None
    unit_theoretical_leverage_return: float | None = None
    max_actual_leverage: float | None = None
    avg_actual_leverage: float | None = None
    unit_actual_leverage_return: float | None = None
    start_monthly_std_dev: float | None = None
    index_monthly_std_dev: float | None = None
    index_annualized_return: float | None = None
    start_annualized_return: float | None = None
    index_profit_annual: float | None = None
    start_profit_annual: float | None = None
    index_profit_monthly_percentage: float | None = None
    start_profit_monthly_percentage: float | None = None
    index_avg_monthly_return_common: float | None = None
    start_avg_monthly_return_common: float | None = None
    index_monthly_return_volatility: float | None = None
    start_monthly_return_volatility: float | None = None
    annualized_return_diff: float | None = None
    outperform_year: float | None = None
    monthly_excess_return_percentage_last_return: float | None = None
    avg_monthly_excess_returns: float | None = None
    monthly_excess_volatility: float | None = None
    max_drawdown: float | None = None
    excess_drawdown_winning_rate: float | None = None
    start_drawdown: float | None = None
    start_maximum_number_of_backtest_repair_days: float | None = None
    excess_maximum_number_of_backtest_repair_days: float | None = None
    index_sharpe_ratio: float | None = None
    start_sharpe_ratio: float | None = None
    index_kama_ratio: float | None = None
    start_kama_ratio: float | None = None
    index_sotino_ratio: float | None = None
    start_sotino_ratio: float | None = None
    excess_sharp: float | None = None
    excess_of_promissory_note: float | None = None
    created_at: str | None = None
    updated_at: str | None = None

__all__ = ['DeleteStockParamResultRequestDto', 'GetSingleStockTemplateRequestDto', 'GetStockParamResultListRequestDto', 't_stock_param_result']
