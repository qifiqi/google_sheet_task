# -*- coding: utf-8 -*-
"""股票主站服务基地址（STOCK_BASE_URL）统一解析。

K线 SDK（StockClient/KlineService）、参数回推（StockAPIClient）、代理池
（SmartProxyManager）共用同一台股票主站；所有调用主站的代码都经本模块
解析基地址，基地址唯一来源是应用配置 STOCK_BASE_URL（由 config.py 从
环境变量镜像），历史默认地址常量也只在本模块定义。显式参数优先；
无应用上下文或未配置时由调用方传入各自兜底地址（默认历史默认地址）。
"""

from flask import current_app, has_app_context

# 主站历史默认地址：STOCK_BASE_URL 未配置且调用方未显式指定 fallback 时的兜底。
DEFAULT_STOCK_BASE_URL = 'http://stockapi.stplan.cn'


def resolve_stock_base_url(explicit: str = '', fallback: str = DEFAULT_STOCK_BASE_URL) -> str:
    """解析股票主站基地址：显式参数 > 应用配置 STOCK_BASE_URL > fallback。"""
    if explicit:
        return explicit
    if has_app_context():
        configured = str(current_app.config.get('STOCK_BASE_URL') or '').strip()
        if configured:
            return configured
    return fallback
