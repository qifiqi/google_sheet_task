"""多品回测缓存的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository


class BacktestProductResultCacheRepository(SdkCrudRepository):
    """转换缓存 JSON，并通过小规模分页按业务键读取。"""

    group_name = "param_backtest_product_result_cache"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将回测结果和收益序列序列化为 JSON。"""
        result = dict(payload)
        for field in ("result_json", "returns_json"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后尽可能还原缓存中的结构化结果。"""
        result = dict(record)
        for field in ("result_json", "returns_json"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return result

    def find_by_business_key(self, batch_id: str, cache_key: str) -> dict[str, Any] | None:
        """分页读取远端缓存，并匹配 batch_id 与 cache_key。

        缓存表数据量受业务约束较小，当前服务端未提供业务键筛选接口时按用户
        确认的方式分页匹配；不依赖本地数据库。
        """
        page_index = 1
        page_size = 200
        received = 0
        while True:
            page = self.list_page(
                page_index=page_index,
                page_size=page_size,
                order_field="created_at",
                order_type="desc",
            )
            received += len(page["items"])
            for item in page["items"]:
                if item.get("batch_id") == batch_id and item.get("cache_key") == cache_key:
                    return item
            if not page["items"] or received >= page["total"]:
                return None
            page_index += 1
