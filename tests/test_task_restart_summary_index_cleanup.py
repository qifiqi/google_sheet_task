import json

from app.extensions import db
from app.models import Task, TaskResult, TaskResultSummaryIndex
from app.services.model_summary_service import model_summary_service
from app.services.task.facade import TaskManager


def _task(task_id="task-1", task_type="google_sheet_C5", name="C5-600519-贵州茅台"):
    return Task(id=task_id, name=name, task_type=task_type, status="completed", config="{}")


def _result(task_id="task-1", result_id=1):
    return TaskResult(
        id=result_id,
        task_id=task_id,
        step_index=0,
        parameters=json.dumps({"stock_code": "600519", "A1": "1.8", "B1": "4", "year": "2025-2024"}),
        result=json.dumps({
            "sheet__model": {
                "D2": "20%",
                "D5": "8%",
                "D11": "2%",
            }
        }),
        success=True,
    )


def test_delete_task_explicitly_clears_summary_index_rows(app_factory):
    app = app_factory
    with app.app_context():
        task = _task(task_id="task-delete")
        db.session.add(task)
        db.session.add(_result(task_id=task.id, result_id=10))
        db.session.commit()
        model_summary_service.rebuild(task_id=task.id, reset=True)

        assert TaskResultSummaryIndex.query.filter_by(task_id=task.id).count() == 1

        manager = TaskManager()
        assert manager.delete_task(task.id) is True

        assert db.session.get(Task, task.id) is None
        assert TaskResult.query.filter_by(task_id=task.id).count() == 0
        assert TaskResultSummaryIndex.query.filter_by(task_id=task.id).count() == 0


def test_restart_from_scratch_explicitly_clears_summary_index_rows(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = _task(task_id="task-restart")
        db.session.add(task)
        db.session.add(_result(task_id=task.id, result_id=20))
        db.session.commit()
        model_summary_service.rebuild(task_id=task.id, reset=True)

        task_id = task.id
        assert TaskResultSummaryIndex.query.filter_by(task_id=task_id).count() == 1

        manager = TaskManager()
        monkeypatch.setattr(manager, "start_task", lambda _task_id: True)

        result = manager.restart_task(task_id, resume_from_checkpoint=False)

        assert result["status"] == "success"
        assert TaskResult.query.filter_by(task_id=task_id).count() == 0
        assert TaskResultSummaryIndex.query.filter_by(task_id=task_id).count() == 0
