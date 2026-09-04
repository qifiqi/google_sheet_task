"""任务仪表盘聚合查询服务（已停用数据库聚合，返回假数据）。

原基于本地 ``Task`` ORM 的聚合查询已全部注释保留；当前 SDK 无对应聚合接口，
按要求仪表盘后端直接返回假数据，不再直连数据库。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

# from sqlalchemy import func
#
# from app.models import Task
# from app.utils.task_authorization import filter_task_types_by_action


class TaskDashboardQueryService:
    """管理后台任务仪表盘聚合查询（当前仅返回假数据）。"""

    def get_allowed_task_types(self, user, action: str = "view") -> list[str]:
        """返回空列表假数据；原数据库任务类型聚合与权限过滤注释保留。"""
        # distinct_task_types = [
        #     item[0]
        #     for item in Task.query.with_entities(Task.task_type).distinct().all()
        #     if item and item[0]
        # ]
        # return filter_task_types_by_action(user, action, distinct_task_types)
        return []

    def build_empty_overview(self, now: datetime, days: int = 7) -> dict:
        """生成无可见任务时仍满足前端结构要求的仪表盘数据。"""
        daily_trend = self._build_empty_daily_trend(now, days=days)
        return {
            "success": True,
            "summary": {
                "total_tasks": 0,
                "completed_tasks": 0,
                "running_tasks": 0,
                "error_tasks": 0,
                "cancelled_tasks": 0,
                "pending_tasks": 0,
            },
            "status_distribution": {},
            "task_type_distribution": {},
            "daily_trend": daily_trend,
            "recent_tasks": [],
            "active_tasks": [],
            "checked_at": now.isoformat(),
        }

    def get_recent_task_models(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 10,
    ) -> list:
        """返回空列表假数据；原数据库最近任务查询注释保留。"""
        # return (
        #     Task.query.filter(Task.task_type.in_(list(allowed_task_types)))
        #     .order_by(Task.created_at.desc())
        #     .limit(limit)
        #     .all()
        # )
        return []

    def get_active_task_models(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 6,
    ) -> list:
        """返回空列表假数据；原数据库运行中任务查询注释保留。"""
        # return (
        #     Task.query.filter(
        #         Task.task_type.in_(list(allowed_task_types)),
        #         Task.status == "running",
        #     )
        #     .order_by(Task.created_at.desc())
        #     .limit(limit)
        #     .all()
        # )
        return []

    def get_status_distribution(self, allowed_task_types: Iterable[str]) -> dict[str, int]:
        """返回空分布假数据；原数据库状态聚合注释保留。"""
        # rows = (
        #     Task.query.with_entities(Task.status, func.count(Task.id))
        #     .filter(Task.task_type.in_(list(allowed_task_types)))
        #     .group_by(Task.status)
        #     .all()
        # )
        # return {status: count for status, count in rows if status}
        return {}

    def get_task_type_distribution(
        self,
        allowed_task_types: Iterable[str],
    ) -> dict[str, int]:
        """返回空分布假数据；原数据库任务类型聚合注释保留。"""
        # rows = (
        #     Task.query.with_entities(Task.task_type, func.count(Task.id))
        #     .filter(Task.task_type.in_(list(allowed_task_types)))
        #     .group_by(Task.task_type)
        #     .all()
        # )
        # return {task_type: count for task_type, count in rows if task_type}
        return {}

    def get_summary(self, allowed_task_types: Iterable[str]) -> dict[str, int]:
        """返回全零汇总假数据；原状态分布转换逻辑注释保留。"""
        # status_distribution = self.get_status_distribution(allowed_task_types)
        # return {
        #     "total_tasks": sum(status_distribution.values()),
        #     "completed_tasks": status_distribution.get("completed", 0),
        #     "running_tasks": status_distribution.get("running", 0),
        #     "error_tasks": status_distribution.get("error", 0),
        #     "cancelled_tasks": status_distribution.get("cancelled", 0),
        #     "pending_tasks": status_distribution.get("pending", 0),
        # }
        return {
            "total_tasks": 0,
            "completed_tasks": 0,
            "running_tasks": 0,
            "error_tasks": 0,
            "cancelled_tasks": 0,
            "pending_tasks": 0,
        }

    def get_daily_trend(
        self,
        allowed_task_types: Iterable[str],
        now: datetime | None = None,
        days: int = 7,
    ) -> list[dict[str, int | str]]:
        """返回全零每日趋势假数据；原数据库按日聚合注释保留。"""
        # reference_time = now or datetime.now()
        # trend_map = self._build_empty_daily_map(reference_time, days=days)
        # start_time = (reference_time - timedelta(days=days - 1)).replace(
        #     hour=0,
        #     minute=0,
        #     second=0,
        #     microsecond=0,
        # )
        # allowed_types = list(allowed_task_types)
        #
        # created_rows = (
        #     Task.query.with_entities(
        #         func.date(Task.created_at),
        #         func.count(Task.id),
        #     )
        #     .filter(
        #         Task.task_type.in_(allowed_types),
        #         Task.created_at >= start_time,
        #     )
        #     .group_by(func.date(Task.created_at))
        #     .all()
        # )
        # completed_rows = (
        #     Task.query.with_entities(
        #         func.date(Task.end_time),
        #         func.count(Task.id),
        #     )
        #     .filter(
        #         Task.task_type.in_(allowed_types),
        #         Task.status == "completed",
        #         Task.end_time.isnot(None),
        #         Task.end_time >= start_time,
        #     )
        #     .group_by(func.date(Task.end_time))
        #     .all()
        # )
        #
        # for bucket_date, count in created_rows:
        #     date_key = self._normalize_date_key(bucket_date)
        #     if date_key in trend_map:
        #         trend_map[date_key]["created"] = int(count)
        #
        # for bucket_date, count in completed_rows:
        #     date_key = self._normalize_date_key(bucket_date)
        #     if date_key in trend_map:
        #         trend_map[date_key]["completed"] = int(count)
        #
        # return [
        #     {
        #         "date": date_key,
        #         "created": values["created"],
        #         "completed": values["completed"],
        #     }
        #     for date_key, values in trend_map.items()
        # ]
        return self._build_empty_daily_trend(now or datetime.now(), days=days)

    def _build_empty_daily_trend(
        self,
        now: datetime,
        days: int = 7,
    ) -> list[dict[str, int | str]]:
        """将空的每日统计映射转换为前端趋势数组。"""
        return [
            {
                "date": date_key,
                "created": values["created"],
                "completed": values["completed"],
            }
            for date_key, values in self._build_empty_daily_map(now, days=days).items()
        ]

    def _build_empty_daily_map(
        self,
        now: datetime,
        days: int = 7,
    ) -> dict[str, dict[str, int]]:
        """为指定天数预先建立创建数和完成数均为零的日期映射。"""
        day_range = [
            (now - timedelta(days=offset)).date()
            for offset in range(days - 1, -1, -1)
        ]
        return {
            day.isoformat(): {"created": 0, "completed": 0}
            for day in day_range
        }

    def _normalize_date_key(self, raw_date) -> str:
        """将数据库日期对象统一转换为趋势图使用的 ISO 日期键。"""
        if hasattr(raw_date, "isoformat"):
            return raw_date.isoformat()
        return str(raw_date)
