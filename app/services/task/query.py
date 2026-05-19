"""任务只读查询服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import or_

from app.extensions import db
from app.models import Task, TaskResult


class TaskQueryService:
    """只读任务查询服务。"""

    def __init__(self, task_manager):
        self._task_manager = task_manager

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        task = db.session.get(Task, task_id)
        if not task:
            return None
        return task.to_dict()

    def get_all_tasks(
        self,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter_by(task_type=task_type)

        tasks = query.order_by(Task.created_at.desc()).all()
        return [task.to_dict() for task in tasks]

    def get_tasks_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        page = max(page or 1, 1)
        per_page = max(min(per_page or 10, 100), 1)

        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter(Task.task_type == task_type)

        if status and status != "all":
            query = query.filter(Task.status == status)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                pattern = f"%{keyword}%"
                query = query.filter(
                    or_(
                        Task.name.ilike(pattern),
                        Task.description.ilike(pattern),
                        Task.id.ilike(pattern),
                    )
                )

        ordered_query = query.order_by(Task.created_at.desc())
        pagination = ordered_query.paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )
        items = [task.to_dict() for task in pagination.items]

        total = query.count()
        completed_tasks = query.filter(Task.status == "completed").count()
        running_tasks = query.filter(Task.status == "running").count()
        error_tasks = query.filter(Task.status == "error").count()
        pending_tasks = query.filter(
            Task.status == "pending",
            Task.current_step > 0,
        ).count()

        today_start = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        tomorrow_start = today_start + timedelta(days=1)
        today_new_tasks = query.filter(
            Task.created_at >= today_start,
            Task.created_at < tomorrow_start,
        ).count()

        completed_with_duration = query.filter(
            Task.status == "completed",
            Task.start_time.isnot(None),
            Task.end_time.isnot(None),
        ).all()
        duration_minutes = []
        for task in completed_with_duration:
            if task.start_time and task.end_time and task.end_time > task.start_time:
                duration_minutes.append(
                    (task.end_time - task.start_time).total_seconds() / 60
                )

        avg_duration_minutes = (
            round(sum(duration_minutes) / len(duration_minutes))
            if duration_minutes
            else 0
        )
        success_rate = (
            round((completed_tasks / (completed_tasks + error_tasks) * 100), 1)
            if (completed_tasks + error_tasks) > 0
            else 0
        )
        error_rate = round((error_tasks / total * 100), 1) if total > 0 else 0

        return {
            "tasks": items,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_prev": pagination.has_prev,
                "has_next": pagination.has_next,
                "prev_num": pagination.prev_num,
                "next_num": pagination.next_num,
            },
            "statistics": {
                "total_tasks": total,
                "completed_tasks": completed_tasks,
                "running_tasks": running_tasks,
                "error_tasks": error_tasks,
                "pending_tasks": pending_tasks,
                "today_new_tasks": today_new_tasks,
                "success_rate": success_rate,
                "error_rate": error_rate,
                "avg_duration_minutes": avg_duration_minutes,
            },
        }

    def check_local_task_status(self, task_id: str) -> dict[str, Any]:
        task = db.session.get(Task, task_id)
        if not task:
            return {"status": "not_found", "message": "任务不存在"}

        db_status = task.status
        thread = self._task_manager.running_tasks.get(task_id)
        memory_running = bool(thread and thread.is_alive())
        latest_result = (
            TaskResult.query.filter_by(task_id=task_id)
            .order_by(TaskResult.timestamp.desc())
            .first()
        )

        latest_log_time = None
        task_logs = self._task_manager.get_task_logs(task_id)
        if task_logs:
            latest_log_time = task_logs[-1]["timestamp"]

        status_check = {
            "task_id": task_id,
            "db_status": db_status,
            "memory_running": memory_running,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "latest_result_time": (
                latest_result.timestamp.isoformat() if latest_result else None
            ),
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
