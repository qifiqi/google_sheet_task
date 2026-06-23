"""任务日志相关能力。"""

from __future__ import annotations

from flask import current_app

from app.extensions import db
from app.models import TaskLog
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
        """
        try:
            if app:
                with app.app_context():
                    log = TaskLog(task_id=task_id, level=level, message=message)
                    db.session.add(log)
                    db.session.commit()
                return

            with current_app.app_context():
                log = TaskLog(task_id=task_id, level=level, message=message)
                db.session.add(log)
                db.session.commit()
        except Exception as exc:
            logger.error("添加任务日志失败: %s", exc)

    def get_task_logs(self, task_id: str, limit: int = 500) -> list[dict]:
        """按时间正序返回最新任务日志。"""
        try:
            logs = (
                TaskLog.query.filter_by(task_id=task_id)
                .order_by(TaskLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            logs.reverse()
            return [log.to_dict() for log in logs]
        except Exception as exc:
            logger.error("获取任务日志失败: %s", exc)
            return []
