import json
import threading
from datetime import datetime

from app.extensions import db
from app.models import GoogleSheet, Task, TaskLog, TaskResult, TaskResultReturn, XplAnalysisJob
from app.services.task.facade import TaskManager
from app.services.xpl_analysis_job_service import XplAnalysisJobStatus


class _FakeThread:
    def __init__(self, should_raise=False):
        self.should_raise = should_raise
        self.started = False
        self.name = "fake-thread"

    def start(self):
        if self.should_raise:
            raise RuntimeError("thread boom")
        self.started = True

    def is_alive(self):
        return self.started

    def join(self, timeout=None):
        self.started = False


def _task(task_id="task-1", *, status="pending", task_type="google_sheet", config=None):
    return Task(
        id=task_id,
        name=task_id,
        description="",
        task_type=task_type,
        status=status,
        config=json.dumps(config or {}, ensure_ascii=False),
        created_at=datetime.now(),
    )


def test_create_task_normalizes_c4_config_and_acquires_sheet(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        sheet = GoogleSheet(name="C4 Sheet", spreadsheet_id="sheet-1", table_type="c4")
        db.session.add(sheet)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(
            "app.services.task.creation.get_google_sheet_token_service",
            lambda: type("TokenSvc", (), {"prepare_task_config": lambda self, config: config})(),
        )

        task_id = manager.create_task(
            "c4",
            "",
            "google_sheet_C4",
            {
                "google_sheet_id": sheet.id,
                "spreadsheet_id": "legacy-id",
                "sheet_name": "legacy-name",
                "parameters": [["1"]],
            },
        )

        task = db.session.get(Task, task_id)
        config = json.loads(task.config)
        sheet = db.session.get(GoogleSheet, sheet.id)

        assert task.task_type == "google_sheet_C4"
        assert config["token_task_type"] == "google_sheet"
        assert "spreadsheet_id" not in config
        assert "sheet_name" not in config
        assert sheet.is_in_use is True
        assert sheet.current_task_id == task_id


def test_start_task_rejects_non_pending_and_records_error(app_factory):
    app = app_factory
    with app.app_context():
        task = _task(status="completed")
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()

        assert manager.start_task(task.id) is False
        assert "任务状态不是pending" in manager.get_start_error(task.id)


def test_start_task_thread_failure_releases_runtime_state(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task(config={"token_type": "none"})
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "_get_config", lambda _key, default=None: 5)
        monkeypatch.setattr(manager, "ensure_google_sheet_occupancy", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(manager, "release_google_sheet_occupancy", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            "app.services.task.runtime.threading.Thread",
            lambda *args, **kwargs: _FakeThread(should_raise=True),
        )

        assert manager.start_task(task.id) is False
        assert "任务线程启动失败" in manager.get_start_error(task.id)
        assert task.id not in manager.running_tasks
        assert task.id not in manager.task_stop_events


def test_finalize_task_execution_respects_cancel_signal(app_factory):
    app = app_factory
    with app.app_context():
        task = _task(status="running")
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        event = threading.Event()
        event.set()
        manager.task_stop_events[task.id] = event

        logger = type("Logger", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None})()
        manager._finalize_task_execution(task.id, app, logger, "completed")

        task = db.session.get(Task, task.id)
        assert task.status == "cancelled"
        assert TaskLog.query.filter_by(task_id=task.id).count() == 1


def test_restart_from_scratch_clears_results_and_starts(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task(status="error")
        task.current_step = 7
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            success=True,
            return_series_id=series.id,
        )
        db.session.add(result)
        db.session.flush()
        db.session.add(XplAnalysisJob(
            task_id=task.id,
            task_result_id=result.id,
            return_series_id=series.id,
            status=XplAnalysisJobStatus.PENDING,
        ))
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "check_local_task_status", lambda _task_id: {"can_restart": True})
        monkeypatch.setattr(manager, "release_task_token_occupancy", lambda _task_id: None)
        monkeypatch.setattr(manager, "release_google_sheet_occupancy", lambda _task_id: None)
        monkeypatch.setattr(manager, "start_task", lambda _task_id: True)
        deleted_archives = []
        monkeypatch.setattr(
            "app.services.return_series_service.ReturnSeriesService.delete_task_archive",
            lambda _self, task_id: deleted_archives.append(task_id) or True,
        )

        result = manager.restart_task(task.id, resume_from_checkpoint=False)
        task = db.session.get(Task, task.id)

        assert result["status"] == "success"
        assert result["restart_from_step"] == 0
        assert task.current_step == 0
        assert TaskResult.query.filter_by(task_id=task.id).count() == 0
        assert TaskResultReturn.query.filter_by(task_id=task.id).count() == 0
        assert XplAnalysisJob.query.filter_by(task_id=task.id).count() == 0
        assert deleted_archives == [task.id]


def test_cancel_task_marks_pending_xpl_jobs_cancelled(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task(status="running")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            success=True,
            return_series_id=series.id,
        )
        db.session.add(result)
        db.session.flush()
        job = XplAnalysisJob(
            task_id=task.id,
            task_result_id=result.id,
            return_series_id=series.id,
            status=XplAnalysisJobStatus.PENDING,
        )
        db.session.add(job)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "release_task_token_occupancy", lambda _task_id: None)
        monkeypatch.setattr(manager, "release_google_sheet_occupancy", lambda _task_id: None)

        assert manager.cancel_task(task.id) is True
        assert db.session.get(XplAnalysisJob, job.id).status == XplAnalysisJobStatus.CANCELLED


def test_restart_running_task_rejected_when_local_status_disallows(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task(status="running")
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "check_local_task_status", lambda _task_id: {"can_restart": False})

        result = manager.restart_task(task.id, resume_from_checkpoint=True)

        assert result["status"] == "error"
        assert "正在运行中" in result["message"]


def test_delete_task_removes_return_series_archive(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task_id = "delete-archive-task"
        task = _task(task_id=task_id, status="completed")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task_id, returns_json="{}"))
        db.session.commit()

        manager = TaskManager()
        monkeypatch.setattr(manager, "release_task_token_occupancy", lambda _task_id: None)
        monkeypatch.setattr(manager, "release_google_sheet_occupancy", lambda _task_id: None)
        deleted_archives = []
        monkeypatch.setattr(
            "app.services.return_series_service.ReturnSeriesService.delete_task_archive",
            lambda _self, task_id: deleted_archives.append(task_id) or True,
        )

        assert manager.delete_task(task_id) is True
        assert db.session.get(Task, task_id) is None
        assert deleted_archives == [task_id]
