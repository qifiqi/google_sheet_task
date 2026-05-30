from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import BacktestSheetRunLock, GoogleSheet, Task, TaskLog, TaskResult, TaskResultReturn
from app.services.backtest_training_service import BacktestTrainingService
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


def test_backtest_nested_sheet_config_acquires_google_sheet_occupancy(app_factory):
    with app_factory.app_context():
        sheet = GoogleSheet(
            name="backtest-sheet",
            spreadsheet_id="spreadsheet-backtest-1",
            table_type="c3",
            is_active=True,
        )
        db.session.add(sheet)
        db.session.commit()

        manager = TaskManager()
        manager.ensure_google_sheet_occupancy(
            "task-backtest",
            {"sheet": {"spreadsheet_id": "spreadsheet-backtest-1"}},
        )

        refreshed = db.session.get(GoogleSheet, sheet.id)
        assert refreshed.is_in_use is True
        assert refreshed.current_task_id == "task-backtest"


def test_create_backtest_task_allows_busy_sheet_to_queue(app_factory):
    with app_factory.app_context():
        db.session.add(
            GoogleSheet(
                name="busy-backtest-sheet",
                spreadsheet_id="spreadsheet-busy",
                table_type="c3",
                is_active=True,
                is_in_use=True,
                current_task_id="other-task",
            )
        )
        db.session.commit()

        manager = TaskManager()

        task_id = manager.create_task(
            name="backtest",
            description="",
            task_type="backtest_training",
            config={"sheet": {"spreadsheet_id": "spreadsheet-busy"}},
        )

        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == "pending"


def test_backtest_same_sheet_create_and_start_queues_when_running(app_factory):
    with app_factory.app_context():
        running_task = Task(
            id="running-backtest",
            name="running-backtest",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-queue"}}),
            status="running",
            start_time=datetime.now(),
        )
        db.session.add(running_task)
        db.session.commit()

        manager = TaskManager()
        response, status_code = manager.create_and_start_task(
            name="queued-backtest",
            description="",
            task_type="backtest_training",
            config={"sheet": {"spreadsheet_id": "spreadsheet-queue"}},
        )

        queued_task = db.session.get(Task, response["task_id"])
        assert status_code == 200
        assert response["status"] == "success"
        assert response["queued"] is True
        assert queued_task.status == "pending"
        assert "已有回测任务正在运行" in response["message"]


def test_backtest_start_task_blocks_same_sheet_running_task_created_within_one_day(app_factory):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-one-day-running"
        running_task = Task(
            id="running-backtest-day",
            name="running-backtest-day",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="running",
            created_at=datetime.now() - timedelta(minutes=1),
            start_time=datetime.now() - timedelta(minutes=1),
        )
        queued_task = Task(
            id="queued-backtest-day",
            name="queued-backtest-day",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now(),
        )
        db.session.add_all([running_task, queued_task])
        db.session.commit()
        queued_task_id = queued_task.id

        manager = TaskManager()
        started = manager.start_task(queued_task_id)

        refreshed = db.session.get(Task, queued_task_id)
        assert started is False
        assert refreshed.status == "pending"
        assert "已有回测任务正在运行" in manager.get_start_error(queued_task_id)


def test_backtest_start_task_blocks_same_sheet_running_task_older_than_one_day(app_factory):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-old-running"
        running_task = Task(
            id="running-backtest-old",
            name="running-backtest-old",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="running",
            created_at=datetime.now() - timedelta(days=2),
            start_time=datetime.now() - timedelta(days=2),
        )
        queued_task = Task(
            id="queued-backtest-old",
            name="queued-backtest-old",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now(),
        )
        db.session.add_all([running_task, queued_task])
        db.session.commit()
        queued_task_id = queued_task.id

        manager = TaskManager()
        started = manager.start_task(queued_task_id)

        refreshed = db.session.get(Task, queued_task_id)
        assert started is False
        assert refreshed.status == "pending"
        assert "已有回测任务正在运行" in manager.get_start_error(queued_task_id)


def test_backtest_start_task_blocks_existing_sheet_lock(monkeypatch, app_factory, tmp_path):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-file-lock"
        task = Task(
            id="queued-backtest-file-lock",
            name="queued-backtest-file-lock",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        manager = TaskManager()
        db.session.add(
            BacktestSheetRunLock(
                spreadsheet_id=spreadsheet_id,
                task_id="locked-backtest",
                task_type="backtest_training",
            )
        )
        db.session.commit()

        started = manager.start_task(task_id)

        refreshed = db.session.get(Task, task_id)
        assert started is False
        assert refreshed.status == "pending"
        assert "已有回测任务正在运行" in manager.get_start_error(task_id)
        assert "locked-backtest" in manager.get_start_error(task_id)


def test_backtest_start_task_releases_sheet_lock_when_thread_start_fails(
    monkeypatch,
    app_factory,
    tmp_path,
):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-thread-fail-lock"
        task = Task(
            id="backtest-thread-fail-lock",
            name="backtest-thread-fail-lock",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        class _FailThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                raise RuntimeError("thread failed")

            def is_alive(self):
                return False

        manager = TaskManager()
        monkeypatch.setattr("app.services.task.runtime.threading.Thread", _FailThread)

        started = manager.start_task(task_id)

        refreshed = db.session.get(Task, task_id)
        assert started is False
        assert refreshed.status == "pending"
        assert BacktestSheetRunLock.query.filter_by(spreadsheet_id=spreadsheet_id).count() == 0


def test_backtest_start_task_marks_running_before_thread_body(monkeypatch, app_factory, tmp_path):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-pre-mark-running"
        first_task = Task(
            id="first-backtest-pre-mark",
            name="first-backtest-pre-mark",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now() - timedelta(minutes=1),
        )
        second_task = Task(
            id="second-backtest-pre-mark",
            name="second-backtest-pre-mark",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="pending",
            created_at=datetime.now(),
        )
        db.session.add_all([first_task, second_task])
        db.session.commit()
        first_task_id = first_task.id
        second_task_id = second_task.id

        class _NoopThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                return None

            def is_alive(self):
                return True

        monkeypatch.setattr("app.services.task.runtime.threading.Thread", _NoopThread)

        manager = TaskManager()
        assert manager.start_task(first_task_id) is True

        refreshed_first = db.session.get(Task, first_task_id)
        assert refreshed_first.status == "running"

        assert manager.start_task(second_task_id) is False
        refreshed_second = db.session.get(Task, second_task_id)
        assert refreshed_second.status == "pending"
        assert "已有回测任务正在运行" in manager.get_start_error(second_task_id)


def test_restart_task_returns_concrete_start_error(monkeypatch, app_factory):
    with app_factory.app_context():
        task = Task(
            id="restart-start-error",
            name="restart-start-error",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-restart-error"}}),
            status="error",
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        manager = TaskManager()
        manager.start_errors[task_id] = "同一个 Google Sheet 已有回测任务正在运行，当前任务保持待执行: running-task"
        monkeypatch.setattr(manager, "start_task", lambda task_id: False)

        result = manager.restart_task(task_id)

        assert result["status"] == "error"
        assert "同一个 Google Sheet 已有回测任务正在运行" in result["message"]
        assert result["start_error"] == manager.get_start_error(task_id)


def test_running_backtest_checkpoint_restart_queues_when_lock_exists(
    monkeypatch,
    app_factory,
    tmp_path,
):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-running-restart"
        task = Task(
            id="running-backtest-restart-blocked",
            name="running-backtest-restart-blocked",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="running",
            created_at=datetime.now(),
            start_time=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        manager = TaskManager()
        db.session.add(
            BacktestSheetRunLock(
                spreadsheet_id=spreadsheet_id,
                task_id="other-running-lock",
                task_type="backtest_training",
            )
        )
        db.session.commit()

        result = manager.restart_task(task_id, resume_from_checkpoint=True)

        refreshed = db.session.get(Task, task_id)
        assert result["status"] == "error"
        assert "已有回测任务正在运行" in result["message"]
        assert refreshed.status == "pending"


def test_backtest_checkpoint_restart_blocks_other_running_same_sheet(monkeypatch, app_factory):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-restart-same-sheet"
        running_task = Task(
            id="running-backtest-restart-conflict",
            name="running-backtest-restart-conflict",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="running",
            created_at=datetime.now(),
            start_time=datetime.now(),
        )
        restart_task = Task(
            id="cancelled-backtest-restart-conflict",
            name="cancelled-backtest-restart-conflict",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="cancelled",
            created_at=datetime.now(),
        )
        db.session.add_all([running_task, restart_task])
        db.session.commit()
        restart_task_id = restart_task.id

        manager = TaskManager()
        monkeypatch.setattr(
            manager,
            "start_task",
            lambda task_id: pytest.fail("start_task should not be called"),
        )

        result = manager.restart_task(restart_task_id, resume_from_checkpoint=True)

        refreshed = db.session.get(Task, restart_task_id)
        assert result["status"] == "success"
        assert result["queued"] is True
        assert "已有回测任务正在运行" in result["message"]
        assert refreshed.status == "pending"


def test_backtest_restart_stays_pending_when_sheet_lock_exists(
    monkeypatch,
    app_factory,
    tmp_path,
):
    with app_factory.app_context():
        spreadsheet_id = "spreadsheet-restart-file-lock"
        task = Task(
            id="backtest-restart-file-lock",
            name="backtest-restart-file-lock",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": spreadsheet_id}}),
            status="error",
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        manager = TaskManager()
        db.session.add(
            BacktestSheetRunLock(
                spreadsheet_id=spreadsheet_id,
                task_id="running-from-lock",
                task_type="backtest_training",
            )
        )
        db.session.commit()

        result = manager.restart_task(task_id, resume_from_checkpoint=True)

        refreshed = db.session.get(Task, task_id)
        assert result["status"] == "error"
        assert "已有回测任务正在运行" in result["message"]
        assert refreshed.status == "pending"
        assert "running-from-lock" in manager.get_start_error(task_id)


def test_backtest_checkpoint_resume_skips_saved_result_steps(app_factory):
    with app_factory.app_context():
        task = Task(
            id="backtest-resume-skip-saved",
            name="backtest-resume-skip-saved",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-resume"}}),
            status="cancelled",
            current_step=2,
            total_steps=4,
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add_all([
            TaskResult(
                task_id=task.id,
                step_index=0,
                parameters="{}",
                result="{}",
                success=True,
            ),
            TaskResult(
                task_id=task.id,
                step_index=1,
                parameters="{}",
                result="{}",
                success=True,
            ),
        ])
        db.session.commit()

        service = BacktestTrainingService({}, task.id, app=app_factory)

        assert service._resolve_resume_start_index(task) == 2


def test_backtest_checkpoint_resume_retries_step_without_saved_result(app_factory):
    with app_factory.app_context():
        task = Task(
            id="backtest-resume-retry-missing-result",
            name="backtest-resume-retry-missing-result",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-resume-gap"}}),
            status="error",
            current_step=3,
            total_steps=4,
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            success=True,
        ))
        db.session.commit()

        service = BacktestTrainingService({}, task.id, app=app_factory)

        assert service._resolve_resume_start_index(task) == 1


def test_restart_task_from_scratch_clears_backtest_returns(monkeypatch, app_factory):
    with app_factory.app_context():
        task = Task(
            id="backtest-restart-clears-returns",
            name="backtest-restart-clears-returns",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-clear-returns"}}),
            status="error",
            current_step=3,
            total_steps=5,
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            success=True,
        ))
        db.session.add(TaskResultReturn(
            task_id=task.id,
            stock_date="2026-01-01",
            index_return=0.01,
            start_return=0.02,
        ))
        db.session.commit()
        task_id = task.id

        manager = TaskManager()
        monkeypatch.setattr(manager, "start_task", lambda task_id: True)

        result = manager.restart_task(task_id, resume_from_checkpoint=False)

        refreshed = db.session.get(Task, task_id)
        assert result["status"] == "success"
        assert result["restart_from_step"] == 0
        assert refreshed.current_step == 0
        assert TaskResult.query.filter_by(task_id=task_id).count() == 0
        assert TaskResultReturn.query.filter_by(task_id=task_id).count() == 0


def test_backtest_finish_starts_next_pending_same_sheet(monkeypatch, app_factory, tmp_path):
    with app_factory.app_context():
        finished_task = Task(
            id="finished-backtest",
            name="finished-backtest",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-next"}}),
            status="completed",
            end_time=datetime.now(),
        )
        next_task = Task(
            id="next-backtest",
            name="next-backtest",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-next"}}),
            status="pending",
            created_at=datetime.now() - timedelta(minutes=5),
        )
        other_task = Task(
            id="other-backtest",
            name="other-backtest",
            description="",
            task_type="backtest_training",
            config=json.dumps({"sheet": {"spreadsheet_id": "spreadsheet-other"}}),
            status="pending",
            created_at=datetime.now() - timedelta(minutes=10),
        )
        db.session.add_all([finished_task, next_task, other_task])
        db.session.commit()
        finished_task_id = finished_task.id
        next_task_id = next_task.id

        started_task_ids = []
        manager = TaskManager()

        original_start_task = manager.start_task

        def _start_task(task_id):
            started_task_ids.append(task_id)
            return original_start_task(task_id)

        class _NoopThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                return None

            def is_alive(self):
                return True

        monkeypatch.setattr("app.services.task.runtime.threading.Thread", _NoopThread)
        manager.start_task = _start_task

        manager._start_next_pending_backtest_task(finished_task_id, app_factory)

        refreshed_next = db.session.get(Task, next_task_id)
        transition_message = (
            "回测任务 finished-backtest 结束，启动同 sheet 的下一个待执行任务: "
            "next-backtest"
        )
        finished_logs = [log.message for log in TaskLog.query.filter_by(task_id=finished_task_id).all()]
        next_logs = [log.message for log in TaskLog.query.filter_by(task_id=next_task_id).all()]
        assert started_task_ids == ["next-backtest"]
        assert refreshed_next.status == "running"
        assert BacktestSheetRunLock.query.filter_by(
            spreadsheet_id="spreadsheet-next",
            task_id="next-backtest",
        ).count() == 1
        assert transition_message in finished_logs
        assert transition_message in next_logs


def test_create_and_start_releases_sheet_when_start_fails(app_factory):
    with app_factory.app_context():
        sheet = GoogleSheet(
            name="release-on-fail",
            spreadsheet_id="spreadsheet-release",
            table_type="c3",
            is_active=True,
        )
        db.session.add(sheet)
        db.session.commit()
        sheet_id = sheet.id

        manager = TaskManager()
        response, status_code = manager.create_and_start_task(
            name="unsupported",
            description="",
            task_type="unsupported_task",
            config={"spreadsheet_id": "spreadsheet-release"},
        )

        refreshed = db.session.get(GoogleSheet, sheet_id)
        assert status_code == 400
        assert response["status"] == "error"
        assert refreshed.is_in_use is False
        assert refreshed.current_task_id is None


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
