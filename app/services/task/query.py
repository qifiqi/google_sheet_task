"""任务只读查询服务（数据层：task_repository / task_result_repository）。"""

from __future__ import annotations

from typing import Any, Optional

from app.repositories import task_repository, task_result_repository


class TaskQueryService:
    """只读任务查询服务。"""

    def __init__(self, task_manager):
        self._task_manager = task_manager

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        return task_repository.get(task_id)

    def get_all_tasks(
        self,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        return task_repository.list_all(task_type=task_type, task_types=task_types)

    def get_tasks_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        page_data = task_repository.page_with_statistics(
            page=page,
            per_page=per_page,
            task_type=task_type,
            task_types=task_types,
            status=status,
            keyword=keyword,
        )
        aggregates = page_data["aggregates"]
        total = aggregates["total"]
        completed_tasks = aggregates["completed"]
        error_tasks = aggregates["error"]
        duration_count = aggregates["duration_count"]

        avg_duration_minutes = (
            round(aggregates["total_duration_seconds"] / duration_count / 60)
            if duration_count
            else 0
        )
        success_rate = (
            round((completed_tasks / (completed_tasks + error_tasks) * 100), 1)
            if (completed_tasks + error_tasks) > 0
            else 0
        )
        error_rate = round((error_tasks / total * 100), 1) if total > 0 else 0

        return {
            "tasks": page_data["items"],
            "pagination": page_data["pagination"],
            "statistics": {
                "total_tasks": total,
                "completed_tasks": completed_tasks,
                "running_tasks": aggregates["running"],
                "error_tasks": error_tasks,
                "pending_tasks": aggregates["pending_started"],
                "today_new_tasks": aggregates["today_new"],
                "success_rate": success_rate,
                "error_rate": error_rate,
                "avg_duration_minutes": avg_duration_minutes,
            },
        }

    def check_local_task_status(self, task_id: str) -> dict[str, Any]:
        task = task_repository.get(task_id)
        if not task:
            return {"status": "not_found", "message": "任务不存在"}

        db_status = task["status"]
        thread = self._task_manager.running_tasks.get(task_id)
        memory_running = bool(thread and thread.is_alive())

        latest_log_time = None
        task_logs = self._task_manager.get_task_logs(task_id)
        if task_logs:
            latest_log_time = task_logs[-1]["timestamp"]

        status_check = {
            "task_id": task_id,
            "db_status": db_status,
            "memory_running": memory_running,
            "current_step": task["current_step"],
            "total_steps": task["total_steps"],
            "latest_result_time": task_result_repository.latest_time_by_task(task_id),
            "latest_log_time": latest_log_time,
            "can_restart": False,
            "restart_reason": None,
        }

        if db_status == "running" and not memory_running:
            status_check["can_restart"] = True
            status_check["restart_reason"] = "任务在数据库中显示为运行状态，但内存中没有对应的线程"
            return status_check

        if db_status == "running" and memory_running:
            timeout_seconds = self._task_manager._get_config(
                "task_status_check_timeout",
                600,
            )
            from datetime import datetime

            now = datetime.now()
            if latest_log_time:
                try:
                    latest_time = datetime.fromisoformat(latest_log_time)
                    time_diff = now - latest_time
                    if time_diff.total_seconds() > timeout_seconds:
                        timeout_minutes = timeout_seconds // 60
                        status_check["can_restart"] = True
                        status_check["restart_reason"] = (
                            f"任务超过{timeout_minutes}分钟没有日志更新，可能已挂死"
                        )
                        return status_check
                except Exception:
                    pass

            status_check["restart_reason"] = "任务正在正常运行"
            return status_check

        status_reason_map = {
            "pending": "任务处于待执行状态",
            "completed": "任务已完成",
            "error": "任务执行出错",
            "cancelled": "任务已被取消",
        }
        status_check["restart_reason"] = status_reason_map.get(
            db_status,
            f"任务状态: {db_status}",
        )
        return status_check


class TaskQueryMixin:
    """为门面类提供稳定的查询接口。"""

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        return TaskQueryService(self).get_task_status(task_id)

    def get_all_tasks(
        self,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        return TaskQueryService(self).get_all_tasks(
            task_type=task_type,
            task_types=task_types,
        )

    def get_tasks_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        return TaskQueryService(self).get_tasks_paginated(
            page=page,
            per_page=per_page,
            task_type=task_type,
            task_types=task_types,
            status=status,
            keyword=keyword,
        )

    def check_local_task_status(self, task_id: str) -> dict[str, Any]:
        return TaskQueryService(self).check_local_task_status(task_id)
