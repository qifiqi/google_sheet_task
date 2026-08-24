"""任务结果的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository, normalize_bool_fields


class TaskResultRepository(SdkCrudRepository):
    """转换结果与参数 JSON；按 task_id 查询等待 ParamTaskResults/Query。"""

    group_name = "param_task_results"

    def list_results(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        success: bool | None = None,
        task_ids: list[str] | None = None,
        order_field: str = "timestamp",
        order_type: str = "desc",
    ) -> dict[str, Any]:
        """按成功状态和多个任务 UUID 查询结果，支持单字段排序。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
            "order_field": order_field,
            "order_type": order_type,
        }
        if success is not None:
            payload["success"] = success
        if task_ids:
            payload["task_ids"] = [str(task_id) for task_id in task_ids]
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

    def delete_by_task_id(self, task_id: str) -> None:
        """按任务 UUID 删除该任务的全部结果及其关联收益记录。"""
        self.client.call(self.group_name, "delete", {"task_id": str(task_id)})

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """保存前序列化参数和结果中的结构化数据。"""
        result = dict(payload)
        for field in ("parameters", "result"):
            if isinstance(result.get(field), (dict, list)):
                result[field] = json.dumps(result[field], ensure_ascii=False, default=str)
        return result

    def normalize_record(self, record: Mapping[str, Any]) -> RemoteRecord:
        """读取后还原 JSON 字段，并保持旧代码的属性访问方式。"""
        result = normalize_bool_fields(record, "success")
        for field in ("parameters", "result"):
            if isinstance(result.get(field), str):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return RemoteRecord(result)
