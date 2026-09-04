"""任务结果查询能力（数据层：task_result_repository）。"""

from __future__ import annotations

from app.repositories import task_result_repository


class TaskResultMixin:
    """封装任务结果读取逻辑。"""

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
            counts = task_result_repository.count_by_task_success(task_id)
            page_data = task_result_repository.list_by_task_paginated(task_id, page, per_page)
            return {
                "items": page_data["items"],
                "total": page_data["total"],
                "pages": page_data["pages"],
                "current_page": page_data["current_page"],
                "per_page": page_data["per_page"],
                "total_success": counts["total_success"],
                "total_failed": counts["total_failed"],
            }

        return task_result_repository.list_by_task(task_id)
