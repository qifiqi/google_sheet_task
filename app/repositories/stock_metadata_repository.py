"""股票搜索元数据的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository


class StockMetadataRepository(SdkCrudRepository):
    """负责 ``raw`` 与远端 ``raw_json`` 字段之间的转换。"""
    group_name = "param_stock_metadata"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将原始元数据转换为 JSON 文本，保留中文字符。"""
        result = dict(payload)
        raw = result.pop("raw", None)
        if raw is not None:
            result["raw_json"] = json.dumps(raw, ensure_ascii=False, default=str)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后将 ``raw_json`` 尽可能解析为 ``raw`` 字典。"""
        result = dict(record)
        raw = result.pop("raw_json", None)
        if raw:
            try:
                result["raw"] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                result["raw"] = {}
        else:
            result["raw"] = {}
        return result

    def save_metadata(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """以股票元数据的字段协议保存一条远端记录。"""
        return self.save(self.to_api_payload(payload))

    def find_latest(self, stock_code: str, market_type: str) -> dict[str, Any] | None:
        """按股票代码和市场精确读取最新一条远端元数据。"""
        raw = self.client.call(self.group_name, "get_data_by_page_list", {
            "page_index": 1,
            "page_size": 1,
            "order_field": "updated_at",
            "order_type": "desc",
            "stock_code": str(stock_code).strip().upper(),
            "market_type": str(market_type).strip(),
        })
        page = self._normalize_page(raw)
        return page["items"][0] if page["items"] else None
