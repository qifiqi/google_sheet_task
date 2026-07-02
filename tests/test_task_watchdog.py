from datetime import datetime, timedelta

from app.extensions import db
from app.models import Task, TaskLog
from app.services import task_watchdog as watchdog_module
from app.services.task_watchdog import (
    REASON_LOG_TIMEOUT,
    REASON_RETRYABLE_NETWORK_ERROR,
    REASON_TASK_ERROR,
    TaskWatchdog,
    WATCHDOG_ABANDON_PREFIX,
    _WatchdogConfig,
)
from app.utils.task_error_utils import NETWORK_ERROR_PREFIX, WATCHDOG_RESTART_PREFIX


def _task(task_id, *, status, error_message=None, created_at=None, start_time=None):
    return Task(
        id=task_id,
        name=task_id,
        task_type="google_sheet",
        status=status,
        error_message=error_message,
        created_at=created_at or datetime.now(),
        start_time=start_time,
        config="{}",
    )


class _FakeTaskManager:
    def __init__(self):
        self.logs = []
        self.restarts = []
        self.started = []
        self.running_tasks = {}
        self.task_stop_events = {}

    def add_task_log(self, task_id, level, message, app=None):
        self.logs.append((task_id, level, message))

    def restart_task(self, task_id, resume_from_checkpoint=True):
        self.restarts.append((task_id, resume_from_checkpoint))
        return {"status": "success"}

    def start_task(self, task_id):
        self.started.append(task_id)
        return True

    def get_start_error(self, task_id):
        return "start failed"

    def release_backtest_sheet_locks(self, task_id):
        pass

    def release_task_token_occupancy(self, task_id):
        pass

    def release_google_sheet_occupancy(self, task_id):
        pass


class _FailingRestartTaskManager(_FakeTaskManager):
    def restart_task(self, task_id, resume_from_checkpoint=True):
        self.restarts.append((task_id, resume_from_checkpoint))
        task = db.session.get(Task, task_id)
        if task:
            task.status = "pending"
            task.error_message = None
            db.session.commit()
        return {"status": "error", "message": "queue full"}


def test_watchdog_fetches_only_recent_relevant_tasks(app_factory):
    app = app_factory
    with app.app_context():
        db.session.add_all([
            _task("running-recent", status="running"),
            _task("network-recent", status="error", error_message=f"{NETWORK_ERROR_PREFIX} timeout"),
            _task("plain-error", status="error", error_message="plain"),
            _task("watchdog-cancelled", status="cancelled", error_message=f"{WATCHDOG_RESTART_PREFIX} attempt=1/3"),
            _task("old-running", status="running", created_at=datetime.now() - timedelta(days=10)),
            _task("abandoned-error", status="error", error_message=f"{WATCHDOG_ABANDON_PREFIX} (尝试 3 次): plain"),
        ])
        db.session.commit()

        ids = {task.id for task in TaskWatchdog()._fetch_watched_tasks()}

        assert ids == {
            "running-recent",
            "network-recent",
            "plain-error",
            "watchdog-cancelled",
        }


def test_watchdog_running_task_log_timeout_triggers_force_restart(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("running", status="running", start_time=datetime.now() - timedelta(minutes=60))
        db.session.add(task)
        db.session.add(TaskLog(
            task_id=task.id,
            level="info",
            message="old",
            timestamp=datetime.now() - timedelta(minutes=45),
        ))
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)
        monkeypatch.setattr(watchdog, "_wait_for_task_thread_stop", lambda *_args: True)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        assert fake_manager.started == ["running"]
        assert db.session.get(Task, "running").status == "pending"
        assert watchdog._read_cached_retry_attempts("running") == 1


def test_watchdog_running_task_log_timeout_attempts_are_cached(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("running", status="running", start_time=datetime.now() - timedelta(minutes=60))
        db.session.add(task)
        db.session.add(TaskLog(
            task_id=task.id,
            level="info",
            message="old",
            timestamp=datetime.now() - timedelta(minutes=45),
        ))
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)
        monkeypatch.setattr(watchdog, "_wait_for_task_thread_stop", lambda *_args: True)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )
        task.status = "running"
        task.error_message = None
        db.session.commit()

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        assert fake_manager.started == ["running", "running"]
        assert watchdog._read_cached_retry_attempts("running") == 2


def test_watchdog_retryable_network_error_uses_checkpoint_restart(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("network", status="error", error_message=f"{NETWORK_ERROR_PREFIX} proxy")
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        assert fake_manager.restarts == [("network", True)]
        assert watchdog._read_cached_retry_attempts("network") == 1


def test_watchdog_plain_error_uses_checkpoint_restart(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("plain-error", status="error", error_message="ValueError: bad config")
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        assert fake_manager.restarts == [("plain-error", True)]
        assert watchdog._read_cached_retry_attempts("plain-error") == 1


def test_watchdog_retryable_attempt_limit_abandons_task(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("network", status="error", error_message=f"{NETWORK_ERROR_PREFIX} proxy")
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)
        watchdog._retry_restart_attempts["network"] = 3

        watchdog._restart_retryable_error_task(
            task,
            REASON_RETRYABLE_NETWORK_ERROR,
            max_attempts=3,
        )

        task = db.session.get(Task, "network")
        assert task.status == "error"
        assert "watchdog 已放弃自动重启" in task.error_message
        assert fake_manager.restarts == []


def test_watchdog_plain_error_attempt_limit_abandons_task(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task("plain-error", status="error", error_message="ValueError: bad config")
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)
        watchdog._retry_restart_attempts["plain-error"] = 3

        watchdog._restart_error_task(
            task,
            REASON_TASK_ERROR,
            max_attempts=3,
        )

        task = db.session.get(Task, "plain-error")
        assert task.status == "error"
        assert task.error_message.startswith(WATCHDOG_ABANDON_PREFIX)
        assert fake_manager.restarts == []


def test_watchdog_retryable_restart_failure_stays_watchable(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FailingRestartTaskManager()
    with app.app_context():
        task = _task("network", status="error", error_message=f"{NETWORK_ERROR_PREFIX} proxy")
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        refreshed = db.session.get(Task, "network")
        assert refreshed.status == "error"
        assert refreshed.error_message.startswith(NETWORK_ERROR_PREFIX)
        assert "attempt=1/3" in refreshed.error_message
        assert {item.id for item in watchdog._fetch_watched_tasks()} == {"network"}


def test_watchdog_prunes_retry_attempt_cache(app_factory):
    app = app_factory
    with app.app_context():
        active = _task("active", status="error", error_message=f"{NETWORK_ERROR_PREFIX} proxy")
        old = _task(
            "old",
            status="error",
            error_message=f"{NETWORK_ERROR_PREFIX} proxy",
            created_at=datetime.now() - timedelta(days=10),
        )
        completed = _task("completed", status="completed")
        db.session.add_all([active, old, completed])
        db.session.commit()

        watchdog = TaskWatchdog()
        watchdog._retry_restart_attempts.update({
            "active": 1,
            "old": 2,
            "completed": 3,
            "missing": 4,
        })

        watchdog._prune_retry_attempt_cache()

        assert watchdog._retry_restart_attempts == {"active": 1}


def test_watchdog_previous_force_restart_failure_is_retried(app_factory, monkeypatch):
    app = app_factory
    fake_manager = _FakeTaskManager()
    with app.app_context():
        task = _task(
            "cancelled",
            status="cancelled",
            error_message=f"{WATCHDOG_RESTART_PREFIX} attempt=1/3 reason={REASON_LOG_TIMEOUT}: failed",
        )
        db.session.add(task)
        db.session.commit()

        watchdog = TaskWatchdog()
        monkeypatch.setattr(watchdog_module, "task_manager", fake_manager)
        monkeypatch.setattr(watchdog, "_wait_for_task_thread_stop", lambda *_args: True)

        watchdog._process_watched_task(
            task,
            _WatchdogConfig(True, 60, 30, 0, 3),
        )

        assert fake_manager.started == ["cancelled"]
