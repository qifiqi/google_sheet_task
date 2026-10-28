"""任务日志相关能力（运行期写 Redis 运行态，结束快照回灌后读库）。"""

from __future__ import annotations

from flask import current_app, has_app_context

from app.repositories import task_log_repository
from app.services.task.runtime_state import get_runtime_state_store
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

        任务运行态存在（执行期）写 Redis 日志流，任务结束快照统一回灌数据库；
        非运行期直写数据库。后台线程必须显式传入 app，以确保拥有稳定的应用
        上下文。日志写入失败只记录错误，不允许影响任务执行链。
        """
        try:
            if get_runtime_state_store().has_state(task_id):
                get_runtime_state_store().append_log(task_id, level, message)
                return
        except Exception as exc:
            logger.error("写入任务运行态日志失败: %s", exc)

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

    def get_task_logs(self, task_id: str, limit: int = 500, after_id: int | None = None) -> list[dict]:
        """按时间正序返回最新任务日志；运行中任务读 Redis 运行态，其余读库。

        after_id 提供时只返回其后的新增日志（id asc）——增量拉取语义要求
        以库内自增 id 为界，运行态（Redis 日志流无自增 id）不参与该路径，
        直接走仓储。"""
        if after_id is None:
            try:
                store = get_runtime_state_store()
                if store.has_state(task_id):
                    return store.get_logs(task_id, limit=limit)
            except Exception as exc:
                logger.error("读取任务运行态日志失败: %s", exc)
        try:
            if after_id is not None:
                return task_log_repository.list_by_task_after(task_id, after_id, limit=limit)
            return task_log_repository.list_by_task(task_id, limit=limit)
        except Exception as exc:
            logger.error("获取任务日志失败: %s", exc)
            return []
