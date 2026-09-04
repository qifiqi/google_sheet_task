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

    def refresh_entity(self, entity):
        """重新加载实体状态（乐观锁 update 绕过会话后同步用）。"""
        db.session.refresh(entity)
        return entity

    def list_active_entities(self):
        """活跃任务实体（调度器 add_job 消费实体属性）。"""
        return ScheduledTask.query.filter_by(is_active=True).all()

    def find_by_name_and_function(self, name, task_function):
        """默认任务播种的存在性检查；返回实体或 None。"""
        return (
            ScheduledTask.query
            .filter_by(name=name, task_function=task_function)
            .first()
        )

    def acquire_run_lock(self, task_id, instance_id, now, commit=True):
        """乐观锁获取执行权：仅当 is_running 为假时置位；返回受影响行数。"""
        rows_updated = (
            ScheduledTask.query
            .filter(
                ScheduledTask.id == task_id,
                ScheduledTask.is_running.is_(False),
            )
            .update(
                {
                    "is_running": True,
                    "running_instance_id": instance_id,
                    "last_run_time": now,
                },
                synchronize_session=False,
            )
        )
        if commit:
            self._commit()
        return rows_updated

    def release_run_lock(self, task_id, instance_id, commit=True):
        """按实例释放运行锁。"""
        rows_updated = (
            ScheduledTask.query
            .filter(
                ScheduledTask.id == task_id,
                ScheduledTask.running_instance_id == instance_id,
            )
            .update(
                {"is_running": False, "running_instance_id": None},
                synchronize_session=False,
            )
        )
        if commit:
            self._commit()
        return rows_updated

    def update_next_run(self, task_id, next_run_time, commit=True):
        """仅更新下次执行时间（add_job 场景，不计执行次数）。"""
        return self.update(task_id, {"next_run_time": next_run_time}, commit=commit)

    def record_run(self, task_id, next_run_time, commit=True):
        """累计执行次数并写入下次执行时间。"""
        row = db.session.get(ScheduledTask, task_id)
        if row is None:
            return None
        row.run_count = (row.run_count or 0) + 1
        row.next_run_time = next_run_time
        if commit:
            self._commit()
        return row

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
