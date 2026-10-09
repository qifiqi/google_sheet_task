"""内置K线库（stock_sdk）读写仓储。

app 侧与内置K线库的唯一接缝：``stock_sdk`` 只允许被本包 import，
消费方（目前仅 kline_service）经下列函数读写，client 由调用方持有
（保持既有构造/测试替身注入方式）。wire 字段名（stock_open/stock_max/…）
在本层不做翻译，翻译仍归 ``KlineService.read/write_internal_kline_data``。
"""

from __future__ import annotations

from typing import Any

from stock_sdk import StockClient

_MARKET_API_ATTR = {"cn": "stock_data", "us": "stock_data_us"}


def create_stock_client(base_url: str | None = None) -> StockClient:
    """构造 SDK 客户端；base_url 为空时使用 SDK 自身默认地址。"""
    if base_url:
        return StockClient(base_url=base_url)
    return StockClient()


def _market_api(client: Any, market: str):
    attr = _MARKET_API_ATTR.get(market)
    if attr is None:
        raise ValueError(f"未知K线库市场: {market}")
    return getattr(client, attr)


def get_stock_data_all_list(client: Any, *, market: str, payload: dict[str, Any]):
    """按区间读取内置K线库原始行（wire 字段形态）。"""
    return _market_api(client, market).get_data_all_list(payload)


def upsert_stock_data(client: Any, *, market: str, payload: dict[str, Any]):
    """单行写入/更新内置K线库（SDK modify_or_add 语义）。"""
    return _market_api(client, market).modify_or_add(payload)
