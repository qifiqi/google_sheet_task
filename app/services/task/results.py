"""任务结果查询能力。"""

from __future__ import annotations

from app.models import Task, TaskResult
from app.services.task_result_summary import build_task_result_list_item


class TaskResultMixin:
    """封装任务结果读取逻辑。"""

    def get_task_results(
        self,
        task_id: str,
        page: int | None = None,
        per_page: int | None = None,
        compact: bool = False,
    ):
        """获取任务结果。

        传入分页参数时返回分页结构，否则返回完整结果列表。
        """
        query = (
            TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.step_index.asc())
        )

        if page is not None and per_page is not None:
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            if compact:
                task = Task.query.filter_by(id=task_id).first()
                task_name = task.name if task else None
                task_type = task.task_type if task else None
                items = [
                    build_task_result_list_item(result, task_name, task_type)
                    for result in pagination.items
                ]
            else:
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

        results = query.all()
        return [result.to_dict() for result in results]
