"""Backtest task metadata used by report exports."""

from __future__ import annotations

from typing import Any


def get_backtest_model_version(title: Any) -> str:
    """从任务模板标题解析报告使用的模型版本。"""
    normalized_title = str(title or "").upper()
    if "C7.0.3" in normalized_title:
        return "c7.0.3"
    if "C7" in normalized_title:
        return "c7.0.2"
    if "C5" in normalized_title:
        return "c5"
    if "C4" in normalized_title:
        return "c4"
    if "C3" in normalized_title or "CHARTING:3" in normalized_title:
        return "c3"
    return ""


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
    """C7.0.3 任务配置判定（training/query 两份判定收敛于此，query 版含 sheets 遍历为准）。

    依次看 sheet/top 级 ``c7_model_version``、sheet/top 级标题含 "C7.0.3"、
    以及多 sheet 布局 ``sheets[]`` 逐项版本。
    """
    if not isinstance(config, dict):
        return False
    sheet = config.get("sheet") or {}
    version = str(sheet.get("c7_model_version") or config.get("c7_model_version") or "").strip().lower()
    title = str(sheet.get("title") or config.get("title") or "").upper()
    if version == "c7_0_3" or "C7.0.3" in title:
        return True
    return any(
        str(item.get("c7_model_version") or "").strip().lower() == "c7_0_3"
        for item in config.get("sheets") or []
        if isinstance(item, dict)
    )
