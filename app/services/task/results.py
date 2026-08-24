"""任务结果查询能力。"""

from __future__ import annotations

from app.repositories.task_result_repository import TaskResultRepository

_task_result_repository = TaskResultRepository()


class TaskResultMixin:
    """封装任务结果读取逻辑。"""

    def save_task_result(self, payload):
        """写入一条任务结果。"""
        return _task_result_repository.save(payload)

    def get_task_result(self, result_id: int):
        """按结果主键读取单条结果。"""
        return _task_result_repository.get(result_id)

    def delete_task_result(self, result_id: int):
        """按结果主键删除单条结果。"""
        return _task_result_repository.delete(result_id)

    def get_task_results(
        self,
        task_id: str,
        page: int | None = None,
        per_page: int | None = None,
    ):
        """获取任务结果。

        传入分页参数时返回分页结构，否则返回完整结果列表。
        """
        if page is not None and per_page is not None:
            page_data = _task_result_repository.list_results(
                page_index=max(1, int(page)),
                page_size=max(1, int(per_page)),
                task_ids=[task_id],
                order_field="timestamp",
                order_type="desc",
            )
            success_data = _task_result_repository.list_results(
                page_index=1,
                page_size=1,
                success=True,
                task_ids=[task_id],
                order_field="timestamp",
                order_type="desc",
            )
            total = page_data["total"]
            success_total = success_data["total"]
            failed_total = total - success_total
            pages = (total + max(1, int(per_page)) - 1) // max(1, int(per_page)) if total else 0
            return {
                "items": [item.to_dict() for item in page_data["items"]],
                "total": total,
                "pages": pages,
                "current_page": max(1, int(page)),
                "per_page": max(1, int(per_page)),
                "total_success": success_total,
                "total_failed": failed_total,
            }

        page_index = 1
        results = []
        while True:
            page_data = _task_result_repository.list_results(
                page_index=page_index,
                page_size=200,
                task_ids=[task_id],
                order_field="timestamp",
                order_type="desc",
            )
            results.extend(item.to_dict() for item in page_data["items"])
            if not page_data["items"] or len(results) >= page_data["total"]:
                return results
            page_index += 1
