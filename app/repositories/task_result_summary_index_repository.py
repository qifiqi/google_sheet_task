"""任务结果汇总索引的远程 CRUD 访问。"""

from __future__ import annotations

import json
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import SdkCrudRepository, normalize_bool_fields


class TaskResultSummaryIndexRepository(SdkCrudRepository):
    """转换汇总指标 JSON 与 is_best 布尔字段。"""

    group_name = "param_task_result_summary_index"

    def list_indexes(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        task_id: str | None = None,
        task_result_id: int | None = None,
        task_type: str | None = None,
        is_best: bool | None = None,
        stock_code: str | None = None,
        market_type: str | None = None,
        period_key: str | None = None,
        order_field: str = "result_timestamp",
        order_type: str = "desc",
    ) -> dict[str, Any]:
        """按索引关联条件分页读取远程汇总记录。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": order_field,
            "order_type": order_type,
        }
        for key, value in (
            ("task_id", task_id),
            ("task_result_id", task_result_id),
            ("task_type", task_type),
            ("is_best", is_best),
            ("stock_code", stock_code),
            ("market_type", market_type),
            ("period_key", period_key),
        ):
            if value is not None and value != "":
                payload[key] = value
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前序列化汇总 JSON，并格式化时间字段。"""
        result = dict(payload)
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        for field in ("result_timestamp", "created_at", "updated_at"):
            if isinstance(result.get(field), (date, datetime)):
                result[field] = result[field].isoformat()
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """读取后还原汇总 JSON，并标准化最佳结果标记。"""
        result = normalize_bool_fields(record, "is_best")
        for field in ("metrics_json", "parameter_summary"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return result
