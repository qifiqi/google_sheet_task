"""任务收益序列的远程 CRUD 访问。"""

from __future__ import annotations

from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository


class TaskResultReturnRepository(SdkCrudRepository):
    """转换拆分后的收益序列字段；按 task_id 查询仍等待专用 Query。"""

    group_name = "param_task_results_return"

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前将收益序列日期边界转换为 HTTP 可序列化的 ISO 文本。"""
        result = dict(payload)
        for field in ("start_return_date", "end_return_date"):
            value = result.get(field)
            if isinstance(value, (date, datetime)):
                result[field] = value.isoformat()
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> RemoteRecord:
        """读取后保留拆分字段，并兼容旧代码的属性访问。"""
        return RemoteRecord(record)
