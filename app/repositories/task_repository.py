"""Task 仓储（契约见 docs/design/data-layer-refactor/02 §2.1）。"""
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_

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

    def page_with_statistics(
        self,
        page,
        per_page,
        task_type=None,
        task_types=None,
        status=None,
        keyword=None,
    ):
        """任务分页 + 同过滤条件的聚合统计（task/query.get_tasks_paginated 语义）。

        - status="pending" 特例：仅统计已开跑的待执行任务
          （status == pending AND current_step > 0），分页与统计一致；
        - aggregates 为原始聚合值，比率/舍入等展示计算留在服务层。
        """
        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter(Task.task_type == task_type)

        if status and status != "all":
            if status == "pending":
                query = query.filter(Task.status == "pending", Task.current_step > 0)
            else:
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

        ordered_query = query.order_by(Task.created_at.desc())
        pagination = ordered_query.paginate(
            page=max(page or 1, 1),
            per_page=max(min(per_page or 10, 100), 1),
            error_out=False,
        )
        items = [t.to_dict() for t in pagination.items]

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        stats_row = query.with_entities(
            func.count(Task.id).label('total'),
            func.count(case((Task.status == 'completed', 1))).label('completed'),
            func.count(case((Task.status == 'running', 1))).label('running'),
            func.count(case((Task.status == 'error', 1))).label('error'),
            func.count(case(
                (and_(Task.status == 'pending', Task.current_step > 0), 1)
            )).label('pending'),
            func.count(case(
                (and_(Task.created_at >= today_start, Task.created_at < tomorrow_start), 1)
            )).label('today_new'),
        ).first()

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

        return {
            "items": items,
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
            "aggregates": {
                "total": stats_row.total or 0,
                "completed": stats_row.completed or 0,
                "running": stats_row.running or 0,
                "error": stats_row.error or 0,
                "pending_started": stats_row.pending or 0,
                "today_new": stats_row.today_new or 0,
                "total_duration_seconds": total_duration_seconds,
                "duration_count": duration_count,
            },
        }

    def get_status_value(self, task_id):
        """仅取任务状态值（执行链每步取消检查的热路径）。"""
        row = (
            Task.query.with_entities(Task.status)
            .filter(Task.id == task_id)
            .first()
        )
        return row[0] if row else None

    def get_entity_fresh(self, task_id):
        """过期会话缓存后重读实体（收尾判断用，执行域）。"""
        try:
            db.session.expire_all()
        except Exception:
            pass
        return Task.query.populate_existing().filter(Task.id == task_id).first()

    def list_running_backtest_entities(self):
        """运行中的回测任务实体（populate_existing 保证新鲜）。"""
        return Task.query.populate_existing().filter(
            Task.task_type.in_(["backtest_training", "backtest_multi_product"]),
            Task.status == "running",
        ).all()

    def list_pending_backtest_entities(self, exclude_task_id):
        """待执行回测任务实体（按创建时间先后，接力启动用）。"""
        return Task.query.filter(
            Task.task_type.in_(["backtest_training", "backtest_multi_product"]),
            Task.status == "pending",
            Task.id != exclude_task_id,
        ).order_by(Task.created_at.asc(), Task.id.asc()).all()

    def mark_running_if_not_running(self, task_id, start_time, commit=True):
        """原子置 running（非 running 状态才生效）；返回受影响行数。"""
        rows = Task.query.filter(
            Task.id == task_id,
            Task.status != "running",
        ).update(
            {"status": "running", "start_time": start_time},
            synchronize_session=False,
        )
        if commit:
            self._commit()
        return rows

    def revert_running_to_pending(self, task_id, commit=True):
        """启动失败回退：running → pending 并清 start_time。"""
        rows = Task.query.filter(
            Task.id == task_id,
            Task.status == "running",
        ).update(
            {"status": "pending", "start_time": None},
            synchronize_session=False,
        )
        if commit:
            self._commit()
        return rows

    def mark_running_if_pending(self, task_id, start_time=None, commit=True):
        """仅当任务处于 pending 时置为 running（watchdog 重启发布语义）。"""
        fields = {"status": "running"}
        if start_time is not None:
            fields["start_time"] = start_time
        rows_updated = (
            Task.query.filter(
                Task.id == task_id,
                Task.status == "pending",
            ).update(fields, synchronize_session=False)
        )
        if commit:
            self._commit()
        return rows_updated

    def list_watchdog_tasks(self, created_cutoff, abandon_prefix, restart_prefix):
        """watchdog 巡检任务集（创建窗口内 running/error(未放弃)/cancelled(重启中)）。

        前缀常量由服务层传入（repositories 禁止 import services）；
        实体形态：watchdog 沿用实体属性做判读并复用执行链实体访问。
        """
        from sqlalchemy import not_

        return Task.query.filter(
            Task.created_at >= created_cutoff,
            or_(
                Task.status == "running",
                and_(
                    Task.status == "error",
                    or_(
                        Task.error_message.is_(None),
                        not_(Task.error_message.startswith(abandon_prefix)),
                    ),
                ),
                and_(
                    Task.status == "cancelled",
                    Task.error_message.isnot(None),
                    Task.error_message.startswith(restart_prefix),
                ),
            ),
        ).all()

    def list_entities_by_status(self, status):
        """按状态取任务实体（token 占用快照等执行链消费）。"""
        return Task.query.filter_by(status=status).all()

    def list_watchdog_active_ids(self, created_cutoff):
        """watchdog 重试缓存清理用：窗口内活跃任务 id。"""
        rows = (
            db.session.query(Task.id)
            .filter(
                Task.created_at >= created_cutoff,
                Task.status.in_(["pending", "running", "error", "cancelled"]),
            )
            .all()
        )
        return [row[0] for row in rows]

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

    # ---- 仪表盘聚合（task/dashboard_query 语义） ----

    def list_recent_entities(self, task_types, limit=10, status=None):
        """按类型过滤的最近任务实体。

        实体形态供 task/runtime_view 序列化消费（B3 收敛该消费后评估收敛）。
        """
        query = Task.query.filter(Task.task_type.in_(list(task_types)))
        if status:
            query = query.filter(Task.status == status)
        return (
            query.order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )

    def count_grouped_by_status(self, task_types):
        rows = (
            Task.query.with_entities(Task.status, func.count(Task.id))
            .filter(Task.task_type.in_(list(task_types)))
            .group_by(Task.status)
            .all()
        )
        return {status: count for status, count in rows if status}

    def count_grouped_by_task_type(self, task_types):
        rows = (
            Task.query.with_entities(Task.task_type, func.count(Task.id))
            .filter(Task.task_type.in_(list(task_types)))
            .group_by(Task.task_type)
            .all()
        )
        return {task_type: count for task_type, count in rows if task_type}

    def count_daily_created(self, task_types, start_time):
        rows = (
            Task.query.with_entities(
                func.date(Task.created_at),
                func.count(Task.id),
            )
            .filter(
                Task.task_type.in_(list(task_types)),
                Task.created_at >= start_time,
            )
            .group_by(func.date(Task.created_at))
            .all()
        )
        return [(bucket, count) for bucket, count in rows]

    def count_daily_completed(self, task_types, start_time):
        rows = (
            Task.query.with_entities(
                func.date(Task.end_time),
                func.count(Task.id),
            )
            .filter(
                Task.task_type.in_(list(task_types)),
                Task.status == "completed",
                Task.end_time.isnot(None),
                Task.end_time >= start_time,
            )
            .group_by(func.date(Task.end_time))
            .all()
        )
        return [(bucket, count) for bucket, count in rows]

    def list_by_ids(self, ids):
        if not ids:
            return []
        return [
            t.to_dict()
            for t in Task.query.filter(Task.id.in_(ids)).all()
        ]

    # ---- 写 ----

    def create(self, fields, commit=True):
        task = Task(**fields)
        db.session.add(task)
        if commit:
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
