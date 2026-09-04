"""任务日志相关能力。"""

from __future__ import annotations

from flask import current_app, has_app_context

from app.repositories.task_log_repository import TaskLogRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)
_task_log_repository = TaskLogRepository()


class TaskLogMixin:
    """封装任务日志写入与查询逻辑。"""

    def add_task_log(
        self,
        task_id: str,
        level: str,
        message: str,
        app=None,
    ) -> None:
        """写入一条任务日志。

        后台线程必须显式传入 app，以确保拥有稳定的应用上下文。
        """
        try:
            if has_app_context():
                _task_log_repository.save({"task_id": task_id, "level": level, "message": message})
                return

            if app:
                with app.app_context():
                    _task_log_repository.save({"task_id": task_id, "level": level, "message": message})
                return

            with current_app.app_context():
                _task_log_repository.save({"task_id": task_id, "level": level, "message": message})
        except Exception as exc:
            logger.error("添加任务日志失败: %s", exc)

    def get_task_logs(self, task_id: str, limit: int = 500) -> list[dict]:
        """按时间正序返回指定任务的最新日志。"""
        try:
            page = _task_log_repository.list_logs(
                task_id=task_id,
                page_size=max(1, min(int(limit), 500)),
                order_field="timestamp",
                order_type="desc",
            )
            logs = list(page["items"])
            logs.reverse()
            return [log.to_dict() for log in logs]
        except Exception as exc:
            logger.error("获取任务日志失败: %s", exc)
            return []
