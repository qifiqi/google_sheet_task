"""Backtest task metadata used by report exports."""

from __future__ import annotations

from typing import Any

from app.utils.model_version import normalize_model_version


def get_price_type(price_mode: Any) -> str:
    """将任务中的价格字段转换为报告显示名称。"""
    return {
        "kp_price": "开盘价",
        "sp_price": "收盘价",
        "vwap_price": "加权平均价",
        "random_price": "随机价",
        "ohlc_price": "OHLC（开高低收）",
    }.get(str(price_mode or "").strip().lower(), "")


def is_c7_0_3_config(config: Any) -> bool:
    """C7.0.3 任务配置判定；运行时只读 sheets[].model_version。"""
    if not isinstance(config, dict):
        return False
    return any(
        normalize_model_version(item.get("model_version")) == "c7_0_3"
        for item in config.get("sheets") or []
        if isinstance(item, dict)
    )
