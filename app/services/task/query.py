"""任务只读查询服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import or_, and_, func, case

from app.extensions import db
from app.models import Task
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository


_task_repository = TaskRepository()
_task_result_repository = TaskResultRepository()

class TaskQueryService:
    """只读任务查询服务。"""

    def __init__(self, task_manager):
        """保存任务门面引用，用于读取本进程线程运行状态。"""
        self._task_manager = task_manager

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        """通过远程主键 CRUD 读取一条任务的当前状态。"""
        task = _task_repository.get(task_id)
        if not task:
            return None
        return task.to_dict()

    def get_all_tasks(
        self,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """按任务类型通过 ParamTasks HTTP 分页读取任务。"""
        types = task_types or ([task_type] if task_type else None)
        page_index = 1
        records: list[dict[str, Any]] = []
        while True:
            page = _task_repository.list_tasks(
                page_index=page_index,
                page_size=100,
                task_types=types,
                order_field="created_at",
                order_type="desc",
            )
            records.extend(page["items"])
            if not page["items"] or len(records) >= page["total"]:
                return records
            page_index += 1

    def get_tasks_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        """通过 ParamTasks HTTP 获取列表；统计字段暂沿用仪表盘数据库聚合。"""
        page = max(page or 1, 1)
        per_page = max(min(per_page or 10, 100), 1)

        types = task_types or ([task_type] if task_type else None)
        remote_page = _task_repository.list_tasks(
            page_index=page,
            page_size=per_page,
            task_types=types,
            statuses=[status] if status and status != "all" else None,
            keyword=keyword.strip() if keyword and keyword.strip() else None,
            order_field="created_at",
            order_type="desc",
        )

        # 仪表盘统计暂未迁移到 SDK；保留原有聚合，避免改变现有页面契约。
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

        remote_total = remote_page["total"]
        pages = (remote_total + per_page - 1) // per_page if remote_total else 0
        items = remote_page["items"]

        today_start = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        tomorrow_start = today_start + timedelta(days=1)

        # 单次聚合查询获取所有统计数据（避免多次 COUNT 查询）
        stats_row = query.with_entities(
            func.count(Task.id).label('total'),
            func.count(case((Task.status == 'completed', 1))).label('completed'),
            func.count(case((Task.status == 'running', 1))).label('running'),
            func.count(case((Task.status == 'error', 1))).label('error'),
            func.count(case(
                (Task.status == 'pending', 1)
            )).label('pending'),
            func.count(case(
                (and_(Task.created_at >= today_start, Task.created_at < tomorrow_start), 1)
            )).label('today_new'),
        ).first()

        total = stats_row.total or 0
        completed_tasks = stats_row.completed or 0
        running_tasks = stats_row.running or 0
        error_tasks = stats_row.error or 0
        pending_tasks = stats_row.pending or 0
        today_new_tasks = stats_row.today_new or 0

        completed_durations = query.filter(
            Task.status == 'completed',
            Task.start_time.isnot(None),
            Task.end_time.isnot(None),
        ).with_entities(Task.start_time, Task.end_time).yield_per(1000)
        total_duration_seconds = 0
        duration_count = 0
        for start_time, end_time in completed_durations:
            total_duration_seconds += (end_time - start_time).total_seconds()
            duration_count += 1
        avg_duration_minutes = (
            round(total_duration_seconds / duration_count / 60)
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
            "tasks": items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": remote_total,
                "pages": pages,
                "has_prev": page > 1,
                "has_next": page < pages,
                "prev_num": page - 1 if page > 1 else None,
                "next_num": page + 1 if page < pages else None,
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
        """对照远端任务状态、内存线程和最近执行痕迹，判断是否可重启。"""
        task = _task_repository.get(task_id)
        if not task:
            return {"status": "not_found", "message": "任务不存在"}

        db_status = task.status
        thread = self._task_manager.running_tasks.get(task_id)
        memory_running = bool(thread and thread.is_alive())
        latest_result_page = _task_result_repository.list_results(
            task_ids=[task_id],
            page_size=1,
            order_field="timestamp",
            order_type="desc",
        )
        latest_result = (
            latest_result_page["items"][0]
            if latest_result_page["items"]
            else None
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
        """代理任务状态查询，保持任务门面的既有公开接口。"""
        return TaskQueryService(self).get_task_status(task_id)

    def get_all_tasks(
        self,
        task_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """代理任务列表查询，保持任务门面的既有公开接口。"""
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
        """代理任务分页查询，保持任务门面的既有公开接口。"""
        return TaskQueryService(self).get_tasks_paginated(
            page=page,
            per_page=per_page,
            task_type=task_type,
            task_types=task_types,
            status=status,
            keyword=keyword,
        )

    def check_local_task_status(self, task_id: str) -> dict[str, Any]:
        """代理本地运行态检查，保持任务门面的既有公开接口。"""
        return TaskQueryService(self).check_local_task_status(task_id)
