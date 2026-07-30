"""任务仪表盘聚合查询服务。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import case, false, func

from app.extensions import db
from app.models import (
    BacktestSheetRunLock,
    GoogleSheet,
    GoogleSheetToken,
    ScheduledTask,
    StockMetadata,
    Task,
    TaskLog,
    TaskResult,
    TaskResultSummaryIndex,
    TaskTemplate,
    XplAnalysisJob,
)
from app.utils.task_authorization import filter_task_types_by_action


class TaskDashboardQueryService:
    """集中处理管理后台任务仪表盘聚合查询。"""

    def get_allowed_task_types(self, user, action: str = "view") -> list[str]:
        distinct_task_types = [
            item[0]
            for item in Task.query.with_entities(Task.task_type).distinct().all()
            if item and item[0]
        ]
        return filter_task_types_by_action(user, action, distinct_task_types)

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
            "period": self.build_empty_period(now, days),
            "recent_tasks": [],
            "active_tasks": [],
            "execution_health": {
                "results": self._empty_result_health(),
                "xpl_jobs": self._empty_xpl_health(),
            },
            "resource_health": {},
            "recent_alerts": [],
            "checked_at": now.isoformat(),
        }

    def build_empty_period(self, now: datetime, days: int) -> dict:
        return {
            "days": days,
            "start_at": self._get_period_start(now, days).isoformat(),
            "task_trend": self._build_empty_task_trend(now, days),
            "task_type_status_distribution": [],
            "result_trend": self._build_empty_result_trend(now, days),
        }

    def get_period_overview(
        self,
        allowed_task_types: Iterable[str],
        now: datetime,
        days: int,
    ) -> dict:
        allowed_types = list(allowed_task_types)
        if not allowed_types:
            return self.build_empty_period(now, days)

        return {
            "days": days,
            "start_at": self._get_period_start(now, days).isoformat(),
            "task_trend": self.get_task_trend(allowed_types, now, days),
            "task_type_status_distribution": self.get_task_type_status_distribution(
                allowed_types,
                now,
                days,
            ),
            "result_trend": self.get_result_trend(allowed_types, now, days),
        }

    def get_recent_task_models(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 10,
    ) -> list[Task]:
        return (
            Task.query.filter(Task.task_type.in_(list(allowed_task_types)))
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_active_task_models(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 6,
    ) -> list[Task]:
        return (
            Task.query.filter(
                Task.task_type.in_(list(allowed_task_types)),
                Task.status == "running",
            )
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_status_distribution(self, allowed_task_types: Iterable[str]) -> dict[str, int]:
        rows = (
            Task.query.with_entities(Task.status, func.count(Task.id))
            .filter(Task.task_type.in_(list(allowed_task_types)))
            .group_by(Task.status)
            .all()
        )
        return {status: count for status, count in rows if status}

    def get_task_type_distribution(
        self,
        allowed_task_types: Iterable[str],
    ) -> dict[str, int]:
        rows = (
            Task.query.with_entities(Task.task_type, func.count(Task.id))
            .filter(Task.task_type.in_(list(allowed_task_types)))
            .group_by(Task.task_type)
            .all()
        )
        return {task_type: count for task_type, count in rows if task_type}

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

    def get_execution_health(self, allowed_task_types: Iterable[str]) -> dict:
        allowed_types = list(allowed_task_types)
        if not allowed_types:
            return {
                "results": self._empty_result_health(),
                "xpl_jobs": self._empty_xpl_health(),
            }

        result_total, result_success = (
            db.session.query(
                func.count(TaskResult.id),
                func.coalesce(
                    func.sum(case((TaskResult.success.is_(True), 1), else_=0)),
                    0,
                ),
            )
            .join(Task, Task.id == TaskResult.task_id)
            .filter(Task.task_type.in_(allowed_types))
            .one()
        )
        result_total = int(result_total or 0)
        result_success = int(result_success or 0)

        xpl_rows = (
            db.session.query(XplAnalysisJob.status, func.count(XplAnalysisJob.id))
            .join(Task, Task.id == XplAnalysisJob.task_id)
            .filter(Task.task_type.in_(allowed_types))
            .group_by(XplAnalysisJob.status)
            .all()
        )
        xpl_statuses = {status: int(count) for status, count in xpl_rows if status}
        avg_compute_seconds = (
            db.session.query(func.avg(XplAnalysisJob.compute_elapsed_seconds))
            .join(Task, Task.id == XplAnalysisJob.task_id)
            .filter(
                Task.task_type.in_(allowed_types),
                XplAnalysisJob.status == "completed",
            )
            .scalar()
        )
        xpl_total = sum(xpl_statuses.values())
        xpl_backlog = sum(
            xpl_statuses.get(status, 0)
            for status in ("pending", "running", "retrying")
        )

        return {
            "results": {
                "total": result_total,
                "success": result_success,
                "failed": result_total - result_success,
                "success_rate": (
                    round((result_success / result_total) * 100, 2)
                    if result_total else 0
                ),
            },
            "xpl_jobs": {
                "total": xpl_total,
                "pending": xpl_statuses.get("pending", 0),
                "running": xpl_statuses.get("running", 0),
                "retrying": xpl_statuses.get("retrying", 0),
                "completed": xpl_statuses.get("completed", 0),
                "error": xpl_statuses.get("error", 0),
                "cancelled": xpl_statuses.get("cancelled", 0),
                "backlog": xpl_backlog,
                "avg_compute_seconds": (
                    round(float(avg_compute_seconds), 3)
                    if avg_compute_seconds is not None else None
                ),
            },
        }

    def get_resource_health(
        self,
        user,
        allowed_task_types: Iterable[str],
    ) -> dict:
        permissions = self._get_permissions(user)
        resource_health = {}

        if permissions.intersection({"google_sheet:view", "google_sheet:manage"}):
            sheet_total, sheet_active, sheet_in_use = db.session.query(
                func.count(GoogleSheet.id),
                func.coalesce(
                    func.sum(case((GoogleSheet.is_active.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((GoogleSheet.is_in_use.is_(True), 1), else_=0)),
                    0,
                ),
            ).one()
            token_total, token_active, token_usage = db.session.query(
                func.count(GoogleSheetToken.id),
                func.coalesce(
                    func.sum(case((GoogleSheetToken.is_active.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(func.sum(GoogleSheetToken.current_in_use_count), 0),
            ).one()
            token_available = GoogleSheetToken.query.filter(
                GoogleSheetToken.is_active.is_(True),
                (
                    (GoogleSheetToken.max_usage_count <= 0)
                    | (
                        GoogleSheetToken.current_in_use_count
                        < GoogleSheetToken.max_usage_count
                    )
                ),
            ).count()
            resource_health["google_sheets"] = {
                "total": int(sheet_total or 0),
                "active": int(sheet_active or 0),
                "in_use": int(sheet_in_use or 0),
                "available": max(0, int(sheet_active or 0) - int(sheet_in_use or 0)),
            }
            resource_health["google_sheet_tokens"] = {
                "total": int(token_total or 0),
                "active": int(token_active or 0),
                "available": int(token_available or 0),
                "current_usage": int(token_usage or 0),
            }

        if permissions.intersection({"scheduler:view", "scheduler:manage"}):
            scheduled_total, scheduled_active, scheduled_running = db.session.query(
                func.count(ScheduledTask.id),
                func.coalesce(
                    func.sum(case((ScheduledTask.is_active.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((ScheduledTask.is_running.is_(True), 1), else_=0)),
                    0,
                ),
            ).one()
            next_run_at = (
                db.session.query(func.min(ScheduledTask.next_run_time))
                .filter(ScheduledTask.is_active.is_(True))
                .scalar()
            )
            resource_health["scheduled_tasks"] = {
                "total": int(scheduled_total or 0),
                "active": int(scheduled_active or 0),
                "running": int(scheduled_running or 0),
                "next_run_at": next_run_at.isoformat() if next_run_at else None,
            }

        if permissions.intersection({"backtest:view", "backtest:create"}):
            resource_health["backtest_locks"] = {
                "active": BacktestSheetRunLock.query.count(),
            }

        catalog = {}
        if permissions.intersection({"template:view", "template:manage"}):
            catalog["task_templates"] = TaskTemplate.query.count()
        if permissions.intersection({"backtest:view", "backtest:create"}):
            catalog["stock_metadata"] = StockMetadata.query.count()
        if permissions.intersection({"database:model_summary", "database:manage"}):
            allowed_types = list(allowed_task_types)
            summary_query = TaskResultSummaryIndex.query
            if allowed_types:
                summary_query = summary_query.filter(
                    TaskResultSummaryIndex.task_type.in_(allowed_types)
                )
            else:
                summary_query = summary_query.filter(false())
            catalog["result_summaries"] = summary_query.count()
            catalog["best_summaries"] = summary_query.filter(
                TaskResultSummaryIndex.is_best.is_(True)
            ).count()
        if catalog:
            resource_health["catalog"] = catalog

        return resource_health

    def get_recent_alerts(
        self,
        allowed_task_types: Iterable[str],
        limit: int = 6,
    ) -> list[dict]:
        allowed_types = list(allowed_task_types)
        if not allowed_types:
            return []

        rows = (
            db.session.query(
                TaskLog.id,
                TaskLog.task_id,
                Task.name,
                TaskLog.level,
                TaskLog.message,
                TaskLog.timestamp,
            )
            .join(Task, Task.id == TaskLog.task_id)
            .filter(
                Task.task_type.in_(allowed_types),
                TaskLog.level.in_(("warning", "error")),
            )
            .order_by(TaskLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "task_name": row.name,
                "level": row.level,
                "message": self._summarize_alert_message(row.message),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]

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

        created_rows = (
            Task.query.with_entities(
                func.date(Task.created_at),
                func.count(Task.id),
            )
            .filter(
                Task.task_type.in_(allowed_types),
                Task.created_at >= start_time,
            )
            .group_by(func.date(Task.created_at))
            .all()
        )
        completed_rows = (
            Task.query.with_entities(
                func.date(Task.end_time),
                func.count(Task.id),
            )
            .filter(
                Task.task_type.in_(allowed_types),
                Task.status == "completed",
                Task.end_time.isnot(None),
                Task.end_time >= start_time,
            )
            .group_by(func.date(Task.end_time))
            .all()
        )

        for bucket_date, count in created_rows:
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["created"] = int(count)

        for bucket_date, count in completed_rows:
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

    def get_task_trend(
        self,
        allowed_task_types: Iterable[str],
        now: datetime,
        days: int,
    ) -> list[dict[str, int | str]]:
        trend_map = self._build_empty_task_trend_map(now, days)
        start_time = self._get_period_start(now, days)
        allowed_types = list(allowed_task_types)

        created_rows = (
            Task.query.with_entities(func.date(Task.created_at), func.count(Task.id))
            .filter(
                Task.task_type.in_(allowed_types),
                Task.created_at >= start_time,
            )
            .group_by(func.date(Task.created_at))
            .all()
        )
        terminal_rows = (
            Task.query.with_entities(
                func.date(Task.end_time),
                Task.status,
                func.count(Task.id),
            )
            .filter(
                Task.task_type.in_(allowed_types),
                Task.status.in_(("completed", "error")),
                Task.end_time.isnot(None),
                Task.end_time >= start_time,
            )
            .group_by(func.date(Task.end_time), Task.status)
            .all()
        )

        for bucket_date, count in created_rows:
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["created"] = int(count)

        for bucket_date, status, count in terminal_rows:
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["completed" if status == "completed" else "error"] = int(count)

        return [
            {"date": date_key, **values}
            for date_key, values in trend_map.items()
        ]

    def get_task_type_status_distribution(
        self,
        allowed_task_types: Iterable[str],
        now: datetime,
        days: int,
    ) -> list[dict[str, int | str]]:
        rows = (
            Task.query.with_entities(Task.task_type, Task.status, func.count(Task.id))
            .filter(
                Task.task_type.in_(list(allowed_task_types)),
                Task.created_at >= self._get_period_start(now, days),
            )
            .group_by(Task.task_type, Task.status)
            .all()
        )
        return [
            {"task_type": task_type, "status": status, "count": int(count)}
            for task_type, status, count in rows
            if task_type and status
        ]

    def get_result_trend(
        self,
        allowed_task_types: Iterable[str],
        now: datetime,
        days: int,
    ) -> list[dict[str, int | str]]:
        trend_map = self._build_empty_result_trend_map(now, days)
        rows = (
            db.session.query(
                func.date(TaskResult.timestamp),
                TaskResult.success,
                func.count(TaskResult.id),
            )
            .join(Task, Task.id == TaskResult.task_id)
            .filter(
                Task.task_type.in_(list(allowed_task_types)),
                TaskResult.timestamp >= self._get_period_start(now, days),
            )
            .group_by(func.date(TaskResult.timestamp), TaskResult.success)
            .all()
        )

        for bucket_date, success, count in rows:
            date_key = self._normalize_date_key(bucket_date)
            if date_key in trend_map:
                trend_map[date_key]["success" if success else "failed"] = int(count)

        return [
            {"date": date_key, **values}
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

    def _get_period_start(self, now: datetime, days: int) -> datetime:
        return (now - timedelta(days=days - 1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    def _build_empty_task_trend(
        self,
        now: datetime,
        days: int,
    ) -> list[dict[str, int | str]]:
        return [
            {"date": date_key, **values}
            for date_key, values in self._build_empty_task_trend_map(now, days).items()
        ]

    def _build_empty_task_trend_map(
        self,
        now: datetime,
        days: int,
    ) -> dict[str, dict[str, int]]:
        return {
            day.isoformat(): {"created": 0, "completed": 0, "error": 0}
            for day in [
                (now - timedelta(days=offset)).date()
                for offset in range(days - 1, -1, -1)
            ]
        }

    def _build_empty_result_trend(
        self,
        now: datetime,
        days: int,
    ) -> list[dict[str, int | str]]:
        return [
            {"date": date_key, **values}
            for date_key, values in self._build_empty_result_trend_map(now, days).items()
        ]

    def _build_empty_result_trend_map(
        self,
        now: datetime,
        days: int,
    ) -> dict[str, dict[str, int]]:
        return {
            day.isoformat(): {"success": 0, "failed": 0}
            for day in [
                (now - timedelta(days=offset)).date()
                for offset in range(days - 1, -1, -1)
            ]
        }

    def _normalize_date_key(self, raw_date) -> str:
        if hasattr(raw_date, "isoformat"):
            return raw_date.isoformat()
        return str(raw_date)

    def _get_permissions(self, user) -> set[str]:
        if not user or not hasattr(user, "get_permissions"):
            return set()
        return set(user.get_permissions() or set())

    def _summarize_alert_message(self, message: str | None) -> str:
        compact = " ".join((message or "").split())
        for marker in ("Traceback (most recent call last):", " Traceback "):
            compact = compact.split(marker, 1)[0].strip()
        return compact if len(compact) <= 180 else f"{compact[:177]}..."

    def _empty_result_health(self) -> dict:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0,
        }

    def _empty_xpl_health(self) -> dict:
        return {
            "total": 0,
            "pending": 0,
            "running": 0,
            "retrying": 0,
            "completed": 0,
            "error": 0,
            "cancelled": 0,
            "backlog": 0,
            "avg_compute_seconds": None,
        }
