"""任务结果的远程 CRUD 访问。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository, normalize_bool_fields


class TaskResultRepository(SdkCrudRepository):
    """转换结果与参数 JSON，并提供受限的单任务结果读取。"""

    group_name = "param_task_results"
    MAX_TASK_RESULT_PAGE_SIZE = 200
    MAX_TASK_RESULT_READS = 10_000
    MAX_TARGETED_RESULT_IDS = 500

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

    def list_task_results(
        self,
        task_id: str,
        *,
        success: bool | None = None,
        page_size: int = MAX_TASK_RESULT_PAGE_SIZE,
        max_records: int = MAX_TASK_RESULT_READS,
    ) -> list[RemoteRecord]:
        """读取一个任务的全部结果，始终在 SDK 侧限定 ``task_ids``。

        当前 SDK 仅保证单字段排序，因而这里不承诺 SQL 时代的多字段稳定排序；
        调用方需要的展示顺序在读取完成后按结果字段确定。超出上限会报错，避免
        异常任务造成无界远端读取。
        """
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            raise ValueError("任务 ID 不能为空")
        bounded_page_size = min(max(1, int(page_size)), self.MAX_TASK_RESULT_PAGE_SIZE)
        bounded_max_records = max(1, int(max_records))
        records: list[RemoteRecord] = []
        page_index = 1
        while True:
            page = self.list_results(
                page_index=page_index,
                page_size=bounded_page_size,
                success=success,
                task_ids=[normalized_task_id],
            )
            items = page["items"]
            records.extend(items)
            if len(records) > bounded_max_records:
                raise ValueError(
                    f"任务 {normalized_task_id} 的结果超过安全读取上限 {bounded_max_records}"
                )
            if not items or len(records) >= page["total"]:
                return records
            page_index += 1

    def get_task_results_by_ids(
        self,
        task_id: str,
        result_ids: list[int],
        *,
        max_ids: int = MAX_TARGETED_RESULT_IDS,
    ) -> list[RemoteRecord]:
        """按主键逐条读取并验证所属任务，拒绝跨任务和过大的 ID 请求。"""
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            raise ValueError("任务 ID 不能为空")
        if len(result_ids) > max_ids:
            raise ValueError(f"一次最多读取 {max_ids} 个任务结果")

        records: list[RemoteRecord] = []
        seen_ids: set[int] = set()
        for result_id in result_ids:
            normalized_result_id = self.normalize_id(result_id)
            if normalized_result_id in seen_ids:
                continue
            seen_ids.add(normalized_result_id)
            record = self.get(normalized_result_id)
            if record and str(record.get("task_id") or "") == normalized_task_id:
                records.append(record)
        return records

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
