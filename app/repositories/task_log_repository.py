"""任务日志的远程 CRUD 访问。"""

from typing import Any

from app.repositories.base import RemoteRecord, SdkCrudRepository


class TaskLogRepository(SdkCrudRepository):
    """仅提供标准 CRUD；按 task_id 查询等待 ParamTaskLogs/Query。"""

    group_name = "param_task_logs"

    def list_logs(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        task_id: str | None = None,
        order_field: str = "timestamp",
        order_type: str = "desc",
    ) -> dict[str, Any]:
        """按任务 UUID 分页读取远程日志。"""
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
        """按任务 UUID 删除任务日志。"""
        self.client.call(self.group_name, "delete", {"task_id": str(task_id)})

    def normalize_record(self, record):
        """日志 DTO 保留属性访问，便于兼容旧运行态逻辑。"""
        return RemoteRecord(record)
