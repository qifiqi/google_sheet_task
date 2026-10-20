"""任务异常收尾必须把终态写回仓储（HTTP 模式无 ORM 会话可依赖）。"""
from contextlib import nullcontext

from app.services.task import error_handling


class _FakeTaskRepo:
    def __init__(self):
        self.updates = []

    def update_fields(self, task_id, commit=True, **fields):
        self.updates.append({"task_id": task_id, "fields": fields, "commit": commit})
        return {"id": task_id, **fields}

    def rollback(self):
        pass


class _FakeLogRepo:
    def __init__(self):
        self.logs = []

    def transaction(self):
        return nullcontext()

    def create_log(self, task_id, level, message, commit=True):
        self.logs.append(
            {"task_id": task_id, "level": level, "message": message, "commit": commit}
        )
        return {}

    def rollback(self):
        pass


def test_uncaught_exception_persists_terminal_status(app_factory, monkeypatch):
    task_repo = _FakeTaskRepo()
    log_repo = _FakeLogRepo()
    monkeypatch.setattr(error_handling, "task_repository", task_repo)
    monkeypatch.setattr(error_handling, "task_log_repository", log_repo)

    error_handling.record_task_exception(
        "t1",
        RuntimeError("boom"),
        "unit-test",
        app=app_factory,
    )

    assert len(task_repo.updates) == 1
    update = task_repo.updates[0]
    fields = update["fields"]
    assert update["commit"] is False
    assert fields["status"] == "error"
    assert "boom" in fields["error_message"]
    assert fields["end_time"] is not None
    assert log_repo.logs and log_repo.logs[0]["level"] == "error"
    assert log_repo.logs[0]["commit"] is False
