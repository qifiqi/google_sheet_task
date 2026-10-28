"""Task 仓储（契约见 docs/design/data-layer-refactor/02 §2.1）。"""
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_

from app.extensions import db
from app.exceptions import NotFoundError
from app.models import Task, TaskStatus
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

    def get_latest_task_id_by_type(self, task_type, statuses=None):
        """指定类型的最近一个任务 id（created_at desc, id desc）；statuses 可选过滤；无则 None。"""
        query = Task.query.filter(Task.task_type == task_type)
        if statuses:
            query = query.filter(Task.status.in_(statuses))
        task = query.order_by(Task.created_at.desc(), Task.id.desc()).first()
        return task.id if task else None

    def list_paginated_with_statistics(
        self,
        page,
        per_page,
        task_type=None,
        task_types=None,
        status=None,
        keyword=None,
        stock_code=None,
    ):
        """任务分页 + 同过滤条件的聚合统计（task/query.get_tasks_paginated 语义）。

        - status="pending" 特例：仅统计已开跑的待执行任务
          （status == pending AND current_step > 0），分页与统计一致；
        - stock_code：按 config JSON 文本里的 "stock_code" 键值前缀匹配，
          锚定键名避免误中 product_name/sheet 等其他字段；
          兼容 json.dumps（": "）与 JSON.stringify（":"）两种分隔符；
        - aggregates 为原始聚合值，比率/舍入等展示计算留在服务层。
        """
        query = Task.query
        if task_types:
            query = query.filter(Task.task_type.in_(task_types))
        elif task_type:
            query = query.filter(Task.task_type == task_type)

        if status and status != "all":
            if status == "pending":
                query = query.filter(Task.status == TaskStatus.PENDING.value, Task.current_step > 0)
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

        if stock_code:
            needle = str(stock_code).strip().strip('"').replace("%", "")
            if needle:
                query = query.filter(or_(
                    Task.config.like(f'%"stock_code": "{needle}%'),
                    Task.config.like(f'%"stock_code":"{needle}%'),
                ))

        ordered_query = query.order_by(Task.created_at.desc())
        pagination = ordered_query.paginate(
            page=max(page or 1, 1),
            per_page=max(min(per_page or 10, 100), 1),
            error_out=False,
        )
        items = [t.to_dict() for t in pagination.items]

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        # 时长统计与状态计数合并进同一条聚合（原来把全部已完成任务的起止时间拉到 Python 求和）
        completed_duration_cond = and_(
            Task.status == TaskStatus.COMPLETED.value,
            Task.start_time.isnot(None),
            Task.end_time.isnot(None),
        )
        if db.engine.dialect.name == "mysql":
            duration_seconds = (
                func.unix_timestamp(Task.end_time)
                - func.unix_timestamp(Task.start_time)
            )
        else:
            # PostgreSQL：epoch 即秒
            duration_seconds = (
                func.extract("epoch", Task.end_time)
                - func.extract("epoch", Task.start_time)
            )
        stats_row = query.with_entities(
            func.count(Task.id).label('total'),
            func.count(case((Task.status == TaskStatus.COMPLETED.value, 1))).label('completed'),
            func.count(case((Task.status == TaskStatus.RUNNING.value, 1))).label('running'),
            func.count(case((Task.status == TaskStatus.ERROR.value, 1))).label('error'),
            func.count(case(
                (and_(Task.status == TaskStatus.PENDING.value, Task.current_step > 0), 1)
            )).label('pending'),
            func.count(case(
                (and_(Task.created_at >= today_start, Task.created_at < tomorrow_start), 1)
            )).label('today_new'),
            func.count(case((completed_duration_cond, 1))).label('duration_count'),
            func.sum(case((completed_duration_cond, duration_seconds))).label('total_duration'),
        ).first()
        total_duration_seconds = float(stats_row.total_duration or 0)
        duration_count = stats_row.duration_count or 0

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

    def list_pending_entities(self, exclude_task_id=None):
        """待执行任务实体，按创建时间先后（Sheet 排队接力/启动补跑用）。

        pending 即排队队列本体；占用判定不在本查询内做，由执行锁裁决。
        """
        query = Task.query.filter(Task.status == TaskStatus.PENDING.value)
        if exclude_task_id:
            query = query.filter(Task.id != exclude_task_id)
        return query.order_by(Task.created_at.asc(), Task.id.asc()).all()

    def list_pending_queued_entities(self, queued_prefix: str):
        """带排队标记的 pending 任务（启动期补跑扫描用，FIFO）。"""
        # LIKE 前缀中的 _/% 是通配符（[SHEET_QUEUED] 含 _），需转义防误配。
        escaped_prefix = (
            queued_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        return Task.query.filter(
            Task.status == TaskStatus.PENDING.value,
            Task.error_message.like(f"{escaped_prefix}%", escape="\\"),
        ).order_by(Task.created_at.asc(), Task.id.asc()).all()

    def mark_running_if_not_running(self, task_id, start_time, commit=True):
        """原子置 running（非 running 状态才生效）；返回受影响行数。"""
        rows = Task.query.filter(
            Task.id == task_id,
            Task.status != TaskStatus.RUNNING.value,
        ).update(
            {"status": TaskStatus.RUNNING.value, "start_time": start_time},
            synchronize_session=False,
        )
        if commit:
            self._commit()
        return rows

    def revert_running_to_pending(self, task_id, commit=True):
        """启动失败回退：running → pending 并清 start_time。"""
        rows = Task.query.filter(
            Task.id == task_id,
            Task.status == TaskStatus.RUNNING.value,
        ).update(
            {"status": TaskStatus.PENDING.value, "start_time": None},
            synchronize_session=False,
        )
        if commit:
            self._commit()
        return rows

    def mark_running_if_pending(self, task_id, start_time=None, commit=True):
        """仅当任务处于 pending 时置为 running（watchdog 重启发布语义）。"""
        fields = {"status": TaskStatus.RUNNING.value}
        if start_time is not None:
            fields["start_time"] = start_time
        rows_updated = (
            Task.query.filter(
                Task.id == task_id,
                Task.status == TaskStatus.PENDING.value,
            ).update(fields, synchronize_session=False)
        )
        if commit:
            self._commit()
        return rows_updated

    def list_running_task_entities(self):
        """running 任务实体（启动期死任务对账；属性访问兼容）。"""
        return Task.query.filter_by(status="running").all()

    def list_watchdog_tasks(self, created_cutoff, abandon_prefix, restart_prefix):
        """watchdog 巡检任务集（创建窗口内 running/error(未放弃)/cancelled(重启中)）。

        前缀常量由服务层传入（repositories 禁止 import services）；
        实体形态：watchdog 沿用实体属性做判读并复用执行链实体访问。
        """
        from sqlalchemy import not_

        return Task.query.filter(
            Task.created_at >= created_cutoff,
            or_(
                Task.status == TaskStatus.RUNNING.value,
                and_(
                    Task.status == TaskStatus.ERROR.value,
                    or_(
                        Task.error_message.is_(None),
                        not_(Task.error_message.startswith(abandon_prefix)),
                    ),
                ),
                and_(
                    Task.status == TaskStatus.CANCELLED.value,
                    Task.error_message.isnot(None),
                    Task.error_message.startswith(restart_prefix),
                ),
            ),
        ).all()

    def list_by_status_ordered(self, status, limit):
        """按状态取任务（updated_at desc, created_at desc，钉钉批量重启用）。"""
        return [
            t.to_dict()
            for t in Task.query.filter(Task.status == status)
            .order_by(Task.updated_at.desc(), Task.created_at.desc())
            .limit(limit)
            .all()
        ]

    def count_by_status(self, status):
        """按状态计数（管理端状态统计用）。"""
        return Task.query.filter_by(status=status).count()

    def list_by_name(self, name, limit=2):
        """按名称取任务（updated/created desc，钉钉命令解析用）。"""
        return [
            t.to_dict()
            for t in Task.query.filter(Task.name == name)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        ]

    def list_id_config_by_status(self, status):
        """按状态取 [{id, config}] 投影（token 占用快照消费；避免整行加载
        数十 KB 的 config TEXT 时连带其余列）。"""
        rows = (
            Task.query.with_entities(Task.id, Task.config)
            .filter_by(status=status)
            .all()
        )
        return [{"id": row[0], "config": row[1]} for row in rows]

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

    def list_distinct_task_types(self):
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
                Task.status == TaskStatus.COMPLETED.value,
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
