"""内部 A 股与美股 K 线存储的远程访问。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.repositories.sdk_client import SdkProtocolError, StockSdkAdapter


class StockMarketDataRepository:
    """隔离 KlineService 与生成 SDK 的接口分组、响应格式等细节。"""

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """注入统一 SDK 适配器，生产环境默认使用标准实现。"""
        self.client = client or StockSdkAdapter()

    @staticmethod
    def _group_name(market_type: str) -> str:
        """按市场类型选择 SDK 的 A 股或美股 K 线分组。"""
        return "stock_data" if market_type == "cn" else "stock_data_us"

    def get_all_rows(self, market_type: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        """读取指定市场的全部 K 线行，并校验响应必须为对象列表。"""
        raw = self.client.call(self._group_name(market_type), "get_data_all_list", payload)
        if raw is None:
            return []
        if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
            raise SdkProtocolError("远程 K 线数据响应不是对象列表")
        return [dict(item) for item in raw]

    def save(self, market_type: str, payload: Mapping[str, Any]) -> Any:
        """新增或更新一条指定市场的 K 线记录。"""
        return self.client.call(self._group_name(market_type), "modify_or_add", payload)
