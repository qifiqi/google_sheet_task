"""ScheduledTask 仓储（契约见 docs/design/data-layer-refactor/02 §2.10）。"""
from app.extensions import db
from app.exceptions import NotFoundError
from app.models import ScheduledTask
from app.repositories.base import BaseRepository


class ScheduledTaskRepository(BaseRepository):
    model = ScheduledTask

    # ---- 读 ----

    def count(self):
        return ScheduledTask.query.count()

    def count_active(self):
        return ScheduledTask.query.filter_by(is_active=True).count()

    def list_all(self):
        return [
            row.to_dict()
            for row in ScheduledTask.query.order_by(ScheduledTask.created_at.desc()).all()
        ]

    def list_paginated(self, page, per_page):
        pagination = ScheduledTask.query.order_by(ScheduledTask.created_at.desc()).paginate(
            page=max(page or 1, 1), per_page=max(min(per_page or 10, 100), 1), error_out=False
        )
        return {
            "items": [row.to_dict() for row in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page,
            "per_page": pagination.per_page,
        }

    def get(self, task_id):
        row = db.session.get(ScheduledTask, task_id)
        return row.to_dict() if row else None

    def get_required(self, task_id):
        """替代 get_or_404：HTTP 语义不进数据层，由全局处理器映射 404。"""
        data = self.get(task_id)
        if data is None:
            raise NotFoundError(f"定时任务不存在: {task_id}")
        return data

    def find_due(self, now):
        """到期待执行任务（scheduler_service 扫描语义：启用、未在执行、next_run_time <= now）。"""
        rows = (
            ScheduledTask.query
            .filter(
                ScheduledTask.is_active.is_(True),
                ScheduledTask.is_running.is_(False),
                ScheduledTask.next_run_time.isnot(None),
                ScheduledTask.next_run_time <= now,
            )
            .order_by(ScheduledTask.next_run_time.asc())
            .all()
        )
        return [row.to_dict() for row in rows]

    def stats(self):
        """聚合统计：{total, active}。"""
        return {
            "total": self.count(),
            "active": self.count_active(),
        }

    # ---- 写 ----

    def create(self, fields, commit=True):
        row = ScheduledTask(**fields)
        db.session.add(row)
        if commit:
            self._commit()
        return row.to_dict()

    def update(self, task_id, fields, commit=True):
        row = db.session.get(ScheduledTask, task_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        if commit:
            self._commit()
        return row.to_dict()

    def delete(self, task_id, commit=True):
        row = db.session.get(ScheduledTask, task_id)
        if row is None:
            return False
        db.session.delete(row)
        if commit:
            self._commit()
        return True
