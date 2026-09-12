"""TaskLog 仓储（契约见 docs/design/data-layer-refactor/02 §2.3）。"""
from app.extensions import db
from app.models import TaskLog
from app.repositories.base import BaseRepository


class TaskLogRepository(BaseRepository):
    model = TaskLog

    # ---- 读 ----

    def get_last(self, task_id):
        """最新一条日志（看门狗活性检查）。"""
        row = (
            TaskLog.query.filter_by(task_id=task_id)
            .order_by(TaskLog.timestamp.desc(), TaskLog.id.desc())
            .first()
        )
        return row.to_dict() if row else None

    def list_by_task(self, task_id, limit=500):
        """按时间正序返回最新 limit 条日志（现有 get_task_logs 语义）。"""
        rows = (
            TaskLog.query.filter_by(task_id=task_id)
            .order_by(TaskLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [row.to_dict() for row in reversed(rows)]

    def list_by_task_paginated(self, task_id, page, per_page, level=None):
        query = TaskLog.query.filter_by(task_id=task_id)
        if level:
            query = query.filter_by(level=level)
        pagination = query.order_by(TaskLog.timestamp.desc(), TaskLog.id.desc()).paginate(
            page=max(page or 1, 1), per_page=max(min(per_page or 50, 200), 1), error_out=False
        )
        return {
            "items": [row.to_dict() for row in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page,
            "per_page": pagination.per_page,
        }

    def count_by_task(self, task_id):
        return TaskLog.query.filter_by(task_id=task_id).count()

    def last_write_time(self, task_id):
        """最新日志时间（datetime 或 None）。"""
        row = (
            TaskLog.query.filter_by(task_id=task_id)
            .order_by(TaskLog.timestamp.desc(), TaskLog.id.desc())
            .first()
        )
        return row.timestamp if row else None

    # ---- 写 ----

    def create_log(self, task_id, level, message, commit=True):
        """写入一条任务日志（执行链每步写日志的热路径，性能须与原直写等价）。"""
        log = TaskLog(
            task_id=task_id,
            level=level,
            message=TaskLog.normalize_message(message),
        )
        db.session.add(log)
        if commit:
            self._commit()
        return log.to_dict()

    def delete_by_task(self, task_id, commit=True):
        deleted = (
            TaskLog.query.filter_by(task_id=task_id)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def delete_older_than(self, cutoff, commit=True):
        """清理窗口条件压 SQL 层；返回删除行数。"""
        deleted = (
            TaskLog.query.filter(TaskLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted

    def list_ids_older_than(self, cutoff, limit):
        """到期日志 id 分批读取（调度清理的批量语义）。"""
        rows = (
            TaskLog.query.filter(TaskLog.timestamp < cutoff)
            .limit(limit)
            .all()
        )
        return [row.id for row in rows]

    def delete_by_ids(self, ids, commit=True):
        """按 id 集合删除；返回删除行数。"""
        if not ids:
            return 0
        deleted = (
            TaskLog.query.filter(TaskLog.id.in_(ids))
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted
