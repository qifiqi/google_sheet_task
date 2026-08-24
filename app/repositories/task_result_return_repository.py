"""任务收益序列的远程 CRUD 访问。"""

from __future__ import annotations

from datetime import date, datetime
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository


class TaskResultReturnRepository(SdkCrudRepository):
    """转换拆分后的收益序列字段；按 task_id 查询仍等待专用 Query。"""

    group_name = "param_task_results_return"

    def list_return_series(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        task_id: str | None = None,
        order_field: str = "id",
        order_type: str = "asc",
    ) -> dict[str, Any]:
        """按任务 UUID 分页读取远程收益序列。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": order_field,
            "order_type": order_type,
        }
        if task_id:
            payload["task_id"] = str(task_id)
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

    def delete_by_task_id(self, task_id: str) -> None:
        """按任务 UUID 删除任务拆分后的全部收益序列。"""
        self.client.call(self.group_name, "delete", {"task_id": str(task_id)})

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
