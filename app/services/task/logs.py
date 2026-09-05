"""任务日志相关能力（数据层：task_log_repository）。"""

from __future__ import annotations

from flask import current_app, has_app_context

from app.repositories import task_log_repository
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
        日志写入失败只记录错误，不允许影响任务执行链。
        """
        def _write():
            task_log_repository.create_log(task_id, level, message)

        try:
            if has_app_context():
                _write()
                return

            if app:
                with app.app_context():
                    _write()
                return

            with current_app.app_context():
                _write()
        except Exception as exc:
            logger.error("添加任务日志失败: %s", exc)

    def get_task_logs(self, task_id: str, limit: int = 500) -> list[dict]:
        """按时间正序返回最新任务日志。"""
        try:
            return task_log_repository.list_by_task(task_id, limit=limit)
        except Exception as exc:
            logger.error("获取任务日志失败: %s", exc)
            return []
