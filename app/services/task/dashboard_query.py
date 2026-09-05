"""任务仪表盘聚合查询服务（数据层：task_repository）。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from app.models import Task
from app.repositories import task_repository


class TaskDashboardQueryService:
    """集中处理管理后台任务仪表盘聚合查询。"""

    def get_allowed_task_types(self, user=None, action: str = "view") -> list[str]:
        return [
            task_type
            for task_type in task_repository.list_distinct_task_types()
            if task_type
        ]

    def get_dashboard_counts(self) -> dict[str, int]:
        """admin 首页仪表盘四连 count：{total, completed, running, error}。"""
        return task_repository.summary_counts()

    def get_recent_tasks(self, limit: int = 10) -> list[dict]:
        """admin 首页最近任务列表（dict 形态，created_at 倒序）。"""
        return task_repository.list_recent(limit)

    def build_empty_overview(self, now: datetime, days: int = 7) -> dict:
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
    ) -> list[Task]:
        # 实体形态：runtime_view 序列化消费（B3 收敛）。
        return task_repository.list_recent_entities(allowed_task_types, limit=limit)

    def get_active_task_models(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 6,
    ) -> list[Task]:
        # 实体形态：runtime_view 序列化消费（B3 收敛）。
        return task_repository.list_recent_entities(
            allowed_task_types,
            limit=limit,
            status="running",
        )

    def get_status_distribution(self, allowed_task_types: Iterable[str]) -> dict[str, int]:
        return task_repository.count_grouped_by_status(allowed_task_types)

    def get_task_type_distribution(
        self,
        allowed_task_types: Iterable[str],
    ) -> dict[str, int]:
        return task_repository.count_grouped_by_task_type(allowed_task_types)

    def get_summary(self, allowed_task_types: Iterable[str]) -> dict[str, int]:
        status_distribution = self.get_status_distribution(allowed_task_types)
        return {
            "total_tasks": sum(status_distribution.values()),
            "completed_tasks": status_distribution.get("completed", 0),
            "running_tasks": status_distribution.get("running", 0),
            "error_tasks": status_distribution.get("error", 0),
            "cancelled_tasks": status_distribution.get("cancelled", 0),
            "pending_tasks": status_distribution.get("pending", 0),
        }

    def get_daily_trend(
        self,
        allowed_task_types: Iterable[str],
        now: datetime | None = None,
        days: int = 7,
    ) -> list[dict[str, int | str]]:
        reference_time = now or datetime.now()
        trend_map = self._build_empty_daily_map(reference_time, days=days)
        start_time = (reference_time - timedelta(days=days - 1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        allowed_types = list(allowed_task_types)

        for bucket_date, count in task_repository.count_daily_created(allowed_types, start_time):
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["created"] = int(count)

        for bucket_date, count in task_repository.count_daily_completed(allowed_types, start_time):
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["completed"] = int(count)

        return [
            {
                "date": date_key,
                "created": values["created"],
                "completed": values["completed"],
            }
            for date_key, values in trend_map.items()
        ]

    def _build_empty_daily_trend(
        self,
        now: datetime,
        days: int = 7,
    ) -> list[dict[str, int | str]]:
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
        day_range = [
            (now - timedelta(days=offset)).date()
            for offset in range(days - 1, -1, -1)
        ]
        return {
            day.isoformat(): {"created": 0, "completed": 0}
            for day in day_range
        }

    def _normalize_date_key(self, raw_date) -> str:
        if hasattr(raw_date, "isoformat"):
            return raw_date.isoformat()
        return str(raw_date)
