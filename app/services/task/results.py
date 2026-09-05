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

    def get_results_paginated(self, page: int, per_page: int, task_id: str | None = None):
        """跨任务结果分页列表（/results GET）。"""
        return task_result_repository.list_paginated(page, per_page, task_id=task_id)

    def get_result_detail(self, result_id: int):
        """结果详情（含 task_type 投影）；不存在返回 None。"""
        return task_result_repository.get_with_task_type(result_id)

    def delete_result(self, result_id: int) -> bool:
        """删除结果；不存在返回 False。"""
        return task_result_repository.delete(result_id)
