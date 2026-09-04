"""Task 仓储（契约见 docs/design/data-layer-refactor/02 §2.1）。"""
from sqlalchemy import or_

from app.extensions import db
from app.exceptions import NotFoundError
from app.models import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository):
    model = Task

    # ---- 读 ----

    def get(self, task_id):
        task = db.session.get(Task, task_id)
        return task.to_dict() if task else None

    def get_required(self, task_id):
        task_dict = self.get(task_id)
        if task_dict is None:
            raise NotFoundError(f"任务不存在: {task_id}")
        return task_dict

    def list_all(self, task_type=None, task_types=None):
        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter(Task.task_type == task_type)
        return [t.to_dict() for t in query.order_by(Task.created_at.desc()).all()]

    def list_paginated(
        self,
        page,
        per_page,
        task_type=None,
        task_types=None,
        status=None,
        keyword=None,
    ):
        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter(Task.task_type == task_type)
        if status and status != "all":
            query = query.filter(Task.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            query = query.filter(
                or_(
                    Task.name.ilike(pattern),
                    Task.description.ilike(pattern),
                    Task.id.ilike(pattern),
                )
            )
        pagination = query.order_by(Task.created_at.desc()).paginate(
            page=max(page or 1, 1),
            per_page=max(min(per_page or 10, 100), 1),
            error_out=False,
        )
        return {
            "items": [t.to_dict() for t in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page,
            "per_page": pagination.per_page,
        }

    def count(self):
        return Task.query.count()

    def count_by_status(self, status):
        return Task.query.filter_by(status=status).count()

    def summary_counts(self):
        """admin 仪表盘四连 count 合并：{total, completed, running, error}。"""
        return {
            "total": self.count(),
            "completed": self.count_by_status("completed"),
            "running": self.count_by_status("running"),
            "error": self.count_by_status("error"),
        }

    def recent(self, limit=10):
        return [
            t.to_dict()
            for t in Task.query.order_by(Task.created_at.desc()).limit(limit).all()
        ]

    def distinct_task_types(self):
        rows = db.session.query(Task.task_type).distinct().all()
        return [row[0] for row in rows]

    def list_by_ids(self, ids):
        if not ids:
            return []
        return [
            t.to_dict()
            for t in Task.query.filter(Task.id.in_(ids)).all()
        ]

    # ---- 写 ----

    def create(self, fields):
        task = Task(**fields)
        db.session.add(task)
        self._commit()
        return task.to_dict()

    def update_fields(self, task_id, commit=True, **fields):
        task = db.session.get(Task, task_id)
        if task is None:
            return None
        for key, value in fields.items():
            setattr(task, key, value)
        if commit:
            self._commit()
        return task.to_dict()

    def clear_created_by(self, user_id, commit=False):
        """删用户时置空其创建的任务引用；返回受影响行数。"""
        rowcount = (
            Task.query.filter_by(created_by_user_id=user_id)
            .update({Task.created_by_user_id: None}, synchronize_session=False)
        )
        if commit:
            self._commit()
        return rowcount

    def delete(self, task_id, commit=True):
        task = db.session.get(Task, task_id)
        if task is None:
            return False
        db.session.delete(task)
        if commit:
            self._commit()
        return True
