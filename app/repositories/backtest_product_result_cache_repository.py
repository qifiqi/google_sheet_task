"""多品回测缓存的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository


class BacktestProductResultCacheRepository(SdkCrudRepository):
    """转换缓存 JSON；按业务键读取等待 QueryByBusinessKey 接口。"""

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
