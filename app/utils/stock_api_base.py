# -*- coding: utf-8 -*-
"""股票服务基地址（STOCK_BASE_URL）统一解析。

K线 SDK（StockClient/KlineService）、参数回推（StockAPIClient）、代理池
（SmartProxyManager）共用同一台股票服务；基地址唯一来源是应用配置
STOCK_BASE_URL（由 config.py 从环境变量镜像）。显式参数优先；
无应用上下文或未配置时由调用方传入各自历史默认地址兜底。
"""

from flask import current_app, has_app_context


def resolve_stock_base_url(explicit: str = '', fallback: str = '') -> str:
    """解析股票服务基地址：显式参数 > 应用配置 STOCK_BASE_URL > fallback。"""
    if explicit:
        return explicit
    if has_app_context():
        configured = str(current_app.config.get('STOCK_BASE_URL') or '').strip()
        if configured:
            return configured
    return fallback
