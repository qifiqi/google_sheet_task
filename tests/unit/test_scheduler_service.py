import json
from datetime import datetime, timedelta

from app.extensions import db
from app.models import ScheduledTask, TaskLog, TaskResult
from app.services import scheduled_task_worker
from app.services.scheduler_service import SchedulerService


def _scheduled_task(**overrides):
    data = {
        "name": "cleanup",
        "description": "",
        "cron_expression": "0 0 * * *",
        "task_type": "cleanup",
        "task_function": "cleanup_old_data",
        "task_params": json.dumps({"days": 10}),
        "is_active": True,
    }
    data.update(overrides)
    return ScheduledTask(**data)


class _FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.removed = []

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def add_job(self, func, trigger, id, args, name, replace_existing):
        self.jobs[id] = type("Job", (), {"id": id, "name": name, "next_run_time": datetime(2024, 1, 1)})()

    def remove_job(self, job_id):
        self.removed.append(job_id)
        self.jobs.pop(job_id, None)


def test_scheduler_add_and_remove_job_updates_next_run(app_factory):
    app = app_factory
    with app.app_context():
        task = _scheduled_task()
        db.session.add(task)
        db.session.commit()

        service = SchedulerService()
        service.app = app
        service.is_running = True
        service.scheduler = _FakeScheduler()

        assert service.add_job(task) is True
        assert service.get_job_status(task.id)["id"] == f"scheduled_task_{task.id}"
        assert db.session.get(ScheduledTask, task.id).next_run_time is not None
        assert service.remove_job(task.id) is True


def test_scheduler_run_job_once_requires_running_scheduler():
    service = SchedulerService()

    assert service.run_job_once(1) is False


def test_scheduler_execute_task_locks_and_launches_subprocess(app_factory, monkeypatch):
    app = app_factory
    launched = []
    with app.app_context():
        task = _scheduled_task()
        db.session.add(task)
        db.session.commit()

        service = SchedulerService()
        service.app = app
        monkeypatch.setattr(
            service,
            "_run_task_in_subprocess",
            lambda scheduled_task: launched.append(scheduled_task.id),
        )

        service._execute_task(task.id)

        db.session.expire_all()
        task = db.session.get(ScheduledTask, task.id)
        assert launched == [task.id]
        assert task.is_running is True
        assert task.running_instance_id == service.instance_id
        assert task.run_count == 1


def test_scheduler_execute_task_skips_disabled_or_locked(app_factory, monkeypatch):
    app = app_factory
    launched = []
    with app.app_context():
        disabled = _scheduled_task(is_active=False)
        locked = _scheduled_task(name="locked", is_running=True, running_instance_id="other")
        db.session.add_all([disabled, locked])
        db.session.commit()

        service = SchedulerService()
        service.app = app
        monkeypatch.setattr(service, "_run_task_in_subprocess", lambda scheduled_task: launched.append(scheduled_task.id))

        service._execute_task(disabled.id)
        service._execute_task(locked.id)

        assert launched == []


def test_scheduler_subprocess_failure_releases_lock(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _scheduled_task(is_running=True)
        db.session.add(task)
        db.session.commit()

        service = SchedulerService()
        service.app = app
        service.instance_id = "instance-1"
        task.running_instance_id = service.instance_id
        db.session.commit()

        def fail_popen(*_args, **_kwargs):
            raise RuntimeError("popen failed")

        monkeypatch.setattr("app.services.scheduler_service.subprocess.Popen", fail_popen)
        service._run_task_in_subprocess(task)

        db.session.expire_all()
        task = db.session.get(ScheduledTask, task.id)
        assert task.is_running is False
        assert task.running_instance_id is None


def test_worker_cleanup_old_logs_deletes_only_expired_rows(app_factory, monkeypatch):
    app = app_factory
    monkeypatch.setattr(scheduled_task_worker.time, "sleep", lambda _seconds: None)
    with app.app_context():
        db.session.add(TaskLog(task_id="old", level="info", message="old", timestamp=datetime.now() - timedelta(days=30)))
        db.session.add(TaskLog(task_id="new", level="info", message="new", timestamp=datetime.now()))
        db.session.commit()

        assert scheduled_task_worker.cleanup_old_logs({"days": 10, "batch_size": 1, "delay": 0}) is True
        assert TaskLog.query.filter_by(task_id="old").count() == 0
        assert TaskLog.query.filter_by(task_id="new").count() == 1


def test_worker_execute_unknown_function_releases_lock(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _scheduled_task(task_function="unknown", is_running=True, running_instance_id="worker-1")
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    monkeypatch.setattr(scheduled_task_worker, "create_app", lambda: app)

    assert scheduled_task_worker.execute_task(task_id, "worker-1") is False
    with app.app_context():
        task = db.session.get(ScheduledTask, task_id)
        assert task.is_running is False
        assert task.running_instance_id is None


def test_worker_cleanup_old_results(app_factory, monkeypatch):
    app = app_factory
    monkeypatch.setattr(scheduled_task_worker.time, "sleep", lambda _seconds: None)
    with app.app_context():
        db.session.add(TaskResult(task_id="old", step_index=0, parameters="{}", result="{}", success=True, timestamp=datetime.now() - timedelta(days=30)))
        db.session.add(TaskResult(task_id="new", step_index=0, parameters="{}", result="{}", success=True, timestamp=datetime.now()))
        db.session.commit()

        assert scheduled_task_worker.cleanup_old_results({"days": 10, "batch_size": 1, "delay": 0}) is True
        assert TaskResult.query.filter_by(task_id="old").count() == 0
        assert TaskResult.query.filter_by(task_id="new").count() == 1
