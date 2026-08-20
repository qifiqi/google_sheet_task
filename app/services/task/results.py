"""任务结果查询能力。"""

from __future__ import annotations

from app.models import TaskResult
from app.repositories.task_result_repository import TaskResultRepository

_task_result_repository = TaskResultRepository()


class TaskResultMixin:
    """封装任务结果读取逻辑。"""

    def save_task_result(self, payload):
        """写入一条任务结果；按 task_id 的列表查询仍等待专用 Query。"""
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
        # TODO: 按 task_id、步骤和成功状态读取必须等待 ParamTaskResults/Query，
        # 当前保留 ORM 查询以维持页面语义，禁止 SDK 全表筛选替代。
        query = (
            TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc())
        )

        if page is not None and per_page is not None:
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            items = [result.to_dict() for result in pagination.items]
            total = pagination.total
            success_total = query.filter_by(success=True).count()
            failed_total = total - success_total
            return {
                "items": items,
                "total": total,
                "pages": pagination.pages,
                "current_page": page,
                "per_page": per_page,
                "total_success": success_total,
                "total_failed": failed_total,
            }

        return [result.to_dict() for result in query.all()]
