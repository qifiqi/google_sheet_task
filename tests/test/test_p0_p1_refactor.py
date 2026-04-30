from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import Task, TaskLog
from app.services.task import (
    TaskDashboardQueryService,
    TaskManager,
    TaskQueryService,
    TaskRuntimeViewService,
)
from app.services.task_watchdog import TaskWatchdog
from app import create_app
from app.utils import auth as auth_module


def _create_task(task_id: str = "task-1", status: str = "pending") -> Task:
    task = Task(
        id=task_id,
        name="test-task",
        description="",
        task_type="google_sheet",
        config="{}",
        status=status,
        current_step=1,
        total_steps=3,
    )
    db.session.add(task)
    db.session.commit()
    return task


def _create_custom_task(
    task_id: str,
    task_type: str,
    status: str,
    created_at: datetime,
    end_time: datetime | None = None,
) -> Task:
    task = Task(
        id=task_id,
        name=task_id,
        description="",
        task_type=task_type,
        config="{}",
        status=status,
        current_step=1,
        total_steps=3,
        created_at=created_at,
        end_time=end_time,
    )
    db.session.add(task)
    db.session.commit()
    return task


class _FakeUser:
    """测试用权限用户。"""

    def __init__(self, permissions):
        self._permissions = set(permissions)

    def get_permissions(self):
        return set(self._permissions)


def test_validate_auth_runtime_settings_rejects_default_secret_outside_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", auth_module.DEFAULT_JWT_SECRET)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be configured"):
        auth_module.validate_auth_runtime_settings()


def test_validate_auth_runtime_settings_rejects_disabled_auth_outside_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "safe-secret")

    with pytest.raises(RuntimeError, match="AUTH_ENABLED=false is only allowed"):
        auth_module.validate_auth_runtime_settings()


def test_create_app_allows_safe_auth_settings_outside_development(monkeypatch, sqlite_test_url):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "safe-secret")
    monkeypatch.setenv("DATABASE_URL", sqlite_test_url)

    app = create_app()

    assert app.config["TESTING"] is True


def test_create_app_rejects_default_secret_outside_development(monkeypatch, sqlite_test_url):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", auth_module.DEFAULT_JWT_SECRET)
    monkeypatch.setenv("DATABASE_URL", sqlite_test_url)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be configured"):
        create_app()


def test_task_query_service_marks_orphan_running_task_as_restartable(app_factory):
    with app_factory.app_context():
        task = _create_task(status="running")
        query_service = TaskQueryService(TaskManager())

        status = query_service.check_local_task_status(task.id)

        assert status["can_restart"] is True
        assert "内存中没有对应的线程" in status["restart_reason"]


def test_task_query_service_marks_stale_running_task_as_restartable(app_factory):
    with app_factory.app_context():
        task = _create_task(status="running")
        stale_time = datetime.now() - timedelta(minutes=30)
        db.session.add(TaskLog(task_id=task.id, level="info", message="stale", timestamp=stale_time))
        db.session.commit()

        manager = TaskManager()

        class _AliveThread:
            def is_alive(self):
                return True

        manager.running_tasks[task.id] = _AliveThread()
        manager._get_config = lambda key, default=None: 60 if key == "task_status_check_timeout" else default

        status = TaskQueryService(manager).check_local_task_status(task.id)

        assert status["can_restart"] is True
        assert "没有日志更新" in status["restart_reason"]


def test_finalize_task_execution_prefers_cancelled_state(app_factory):
    with app_factory.app_context():
        task = _create_task(status="running")
        manager = TaskManager()
        manager.task_stop_events[task.id] = type(
            "_StopEvent",
            (),
            {"is_set": staticmethod(lambda: True)},
        )()

        messages = []

        class _Logger:
            def info(self, message):
                messages.append(message)

            def warning(self, message):
                messages.append(message)

        manager.add_task_log = lambda *args, **kwargs: None
        manager._finalize_task_execution(task.id, app_factory, _Logger(), "completed")

        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "cancelled"
        assert any("cancelled" in message for message in messages)


def test_dashboard_overview_filters_unauthorized_task_types(app_factory):
    with app_factory.app_context():
        _create_task(task_id="task-c3", status="completed")
        c4_task = Task(
            id="task-c4",
            name="test-task-c4",
            description="",
            task_type="google_sheet_c4",
            config="{}",
            status="running",
            current_step=0,
            total_steps=1,
        )
        db.session.add(c4_task)
        db.session.commit()

        user = _FakeUser({"task:view", "google_sheet:c3"})
        overview = TaskRuntimeViewService(TaskManager()).build_dashboard_overview(user)

        assert overview["summary"]["total_tasks"] == 1
        assert overview["summary"]["completed_tasks"] == 1
        assert overview["summary"]["running_tasks"] == 0
        assert overview["task_type_distribution"] == {"google_sheet": 1}
        assert len(overview["recent_tasks"]) == 1
        assert overview["recent_tasks"][0]["task_type"] == "google_sheet"


def test_dashboard_query_service_aggregates_by_sql(app_factory):
    with app_factory.app_context():
        now = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        _create_custom_task(
            task_id="task-completed",
            task_type="google_sheet",
            status="completed",
            created_at=now - timedelta(days=1),
            end_time=now,
        )
        _create_custom_task(
            task_id="task-running",
            task_type="google_sheet",
            status="running",
            created_at=now - timedelta(days=2),
        )
        _create_custom_task(
            task_id="task-error",
            task_type="google_sheet_c4",
            status="error",
            created_at=now - timedelta(days=3),
        )

        query_service = TaskDashboardQueryService()

        status_distribution = query_service.get_status_distribution(["google_sheet"])
        task_type_distribution = query_service.get_task_type_distribution(
            ["google_sheet"]
        )
        summary = query_service.get_summary(["google_sheet"])
        daily_trend = query_service.get_daily_trend(["google_sheet"], now=now)

        assert status_distribution == {"completed": 1, "running": 1}
        assert task_type_distribution == {"google_sheet": 2}
        assert summary == {
            "total_tasks": 2,
            "completed_tasks": 1,
            "running_tasks": 1,
            "error_tasks": 0,
            "cancelled_tasks": 0,
            "pending_tasks": 0,
        }

        trend_map = {item["date"]: item for item in daily_trend}
        assert trend_map[(now - timedelta(days=2)).date().isoformat()]["created"] == 1
        assert trend_map[(now - timedelta(days=1)).date().isoformat()]["created"] == 1
        assert trend_map[now.date().isoformat()]["completed"] == 1
        assert (now - timedelta(days=3)).date().isoformat() in trend_map
        assert trend_map[(now - timedelta(days=3)).date().isoformat()]["created"] == 0


def test_watchdog_detects_log_timeout_restart_reason(app_factory):
    with app_factory.app_context():
        stale_log = TaskLog(
            task_id="task-timeout",
            level="info",
            message="stale",
            timestamp=datetime.now() - timedelta(minutes=90),
        )
        task = Task(
            id="task-timeout",
            name="task-timeout",
            description="",
            task_type="google_sheet",
            config="{}",
            status="running",
            current_step=0,
            total_steps=1,
            start_time=datetime.now() - timedelta(minutes=120),
        )
        db.session.add(task)
        db.session.add(stale_log)
        db.session.commit()

        watchdog = TaskWatchdog()
        should_restart, reason = watchdog._has_task_exceeded_log_timeout(
            task,
            stale_log,
            log_timeout_minutes=30,
            now=datetime.now(),
        )

        assert should_restart is True
        assert reason == "log_timeout"


def test_watchdog_detects_missing_initial_log_restart_reason(app_factory):
    with app_factory.app_context():
        task = Task(
            id="task-no-log",
            name="task-no-log",
            description="",
            task_type="google_sheet",
            config="{}",
            status="running",
            current_step=0,
            total_steps=1,
            start_time=datetime.now() - timedelta(minutes=80),
        )
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        should_restart, reason = watchdog._has_task_exceeded_log_timeout(
            task,
            latest_log=None,
            log_timeout_minutes=30,
            now=datetime.now(),
        )

        assert should_restart is True
        assert reason == "missing_initial_log"


def test_watchdog_restart_uses_cancel_then_restart(monkeypatch):
    watchdog = TaskWatchdog()
    events = []

    monkeypatch.setattr(
        "app.services.task_watchdog.task_manager.cancel_task",
        lambda task_id: events.append(("cancel", task_id)) or True,
    )
    monkeypatch.setattr(
        "app.services.task_watchdog.task_manager.restart_task",
        lambda task_id, resume_from_checkpoint=True: (
            events.append(("restart", task_id, resume_from_checkpoint)) or {"status": "success"}
        ),
    )

    watchdog._restart_task_with_reason("task-1", "log_timeout")

    assert events == [
        ("cancel", "task-1"),
        ("restart", "task-1", True),
    ]
