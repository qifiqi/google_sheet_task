from __future__ import annotations

import datetime
from typing import Any, Callable, Optional

from app.models import Task, TaskLog, TaskResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskQueryService:
    """Read-only task queries.

    This service centralizes query-oriented logic so TaskManager can focus on
    orchestration and lifecycle control. The methods here should avoid mutating
    task state.
    """

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        """Return a serialized task snapshot for the given id."""
        task = Task.query.get(task_id)
        if not task:
            return None
        return task.to_dict()

    def get_all_tasks(self, task_type: Optional[str] = None) -> list[dict[str, Any]]:
        """Return serialized tasks, optionally filtered by task_type."""
        query = Task.query
        if task_type:
            query = query.filter_by(task_type=task_type)
        tasks = query.order_by(Task.created_at.desc()).all()
        return [task.to_dict() for task in tasks]

    def get_task_logs(self, task_id: str, limit: int = 500) -> list[dict[str, Any]]:
        """Load recent task logs in chronological order for frontend display."""
        try:
            logs = (
                TaskLog.query
                .filter_by(task_id=task_id)
                .order_by(TaskLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            logs.reverse()
            return [log.to_dict() for log in logs]
        except Exception as exc:
            logger.error(f"获取任务日志失败: {str(exc)}")
            return []

    def get_task_results(self, task_id: str, page: int | None = None, per_page: int | None = None):
        """Return task results, with optional pagination metadata."""
        query = TaskResult.query.filter_by(task_id=task_id).order_by(TaskResult.step_index.asc())

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

        results = query.all()
        return [result.to_dict() for result in results]

    def check_local_task_status(
        self,
        task_id: str,
        running_tasks: dict[str, Any],
        get_task_logs: Callable[[str], list[dict[str, Any]]],
        get_config: Callable[[str, Any], Any],
    ) -> dict[str, Any]:
        """Inspect task state across DB, memory and latest log activity."""
        task = Task.query.get(task_id)
        if not task:
            return {"status": "not_found", "message": "任务不存在"}

        db_status = task.status
        thread = running_tasks.get(task_id)
        memory_running = bool(thread and thread.is_alive())

        latest_result = (
            TaskResult.query
            .filter_by(task_id=task_id)
            .order_by(TaskResult.timestamp.desc())
            .first()
        )

        latest_log_time = None
        task_logs = get_task_logs(task_id)
        if task_logs:
            latest_log_time = task_logs[-1]["timestamp"]

        status_check = {
            "task_id": task_id,
            "db_status": db_status,
            "memory_running": memory_running,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "latest_result_time": latest_result.timestamp.isoformat() if latest_result else None,
            "latest_log_time": latest_log_time,
            "can_restart": False,
            "restart_reason": None,
        }

        if db_status == "running" and not memory_running:
            status_check["can_restart"] = True
            status_check["restart_reason"] = "任务在数据库中显示为运行状态，但内存中没有对应线程"
            return status_check

        if db_status == "running" and memory_running:
            timeout_seconds = get_config("task_status_check_timeout", 600)
            now = datetime.datetime.now()
            if latest_log_time:
                try:
                    latest_time = datetime.datetime.fromisoformat(latest_log_time)
                    time_diff = now - latest_time
                    if time_diff.total_seconds() > timeout_seconds:
                        timeout_minutes = timeout_seconds // 60
                        status_check["can_restart"] = True
                        status_check["restart_reason"] = f"任务超过{timeout_minutes}分钟没有日志更新，可能已挂起"
                    else:
                        status_check["restart_reason"] = "任务正在正常运行"
                except ValueError:
                    status_check["restart_reason"] = "任务正在正常运行"
            else:
                status_check["restart_reason"] = "任务正在正常运行"
            return status_check

        if db_status == "pending":
            status_check["restart_reason"] = "任务处于待执行状态"
        elif db_status == "completed":
            status_check["restart_reason"] = "任务已完成"
        elif db_status == "error":
            status_check["restart_reason"] = "任务执行出错"
        elif db_status == "cancelled":
            status_check["restart_reason"] = "任务已被取消"
        else:
            status_check["restart_reason"] = f"任务状态: {db_status}"

        return status_check


task_query_service = TaskQueryService()
