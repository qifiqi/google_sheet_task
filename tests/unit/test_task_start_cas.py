"""启动时必须 CAS pending→running，不能覆盖取消后的终态。"""
import logging
import threading
from types import SimpleNamespace

from app.services.task import runtime as runtime_module
from app.services.task.facade import TaskManager


class _FakeTaskRepo:
    def __init__(self, status):
        self.row = SimpleNamespace(
            status=status,
            task_type="google_sheet",
            current_step=0,
            total_steps=0,
            start_time=None,
        )
        self.update_calls = []
        self.cas_calls = []

    def get_entity(self, task_id):
        return self.row

    def update_fields(self, task_id, commit=True, **fields):
        self.update_calls.append(fields)
        return dict(fields)

    def mark_running_if_pending(self, task_id, start_time=None, commit=True):
        self.cas_calls.append(start_time)
        if self.row.status != "pending":
            return 0
        self.row.status = "running"
        return 1


def _manager(monkeypatch, status):
    repo = _FakeTaskRepo(status)
    monkeypatch.setattr(runtime_module, "task_repository", repo)
    manager = TaskManager()
    monkeypatch.setattr(manager, "add_task_log", lambda *args, **kwargs: None)
    return manager, repo


def test_cancelled_task_is_not_marked_running(monkeypatch):
    manager, repo = _manager(monkeypatch, "cancelled")

    result = manager._mark_task_running(
        "t1",
        logging.getLogger("test"),
        None,
        "start",
    )

    assert result is None
    assert repo.cas_calls, "必须尝试 CAS pending→running"
    assert not any(fields.get("status") == "running" for fields in repo.update_calls)


def test_stop_requested_during_start_is_not_marked_running(monkeypatch):
    manager, repo = _manager(monkeypatch, "pending")
    stop_event = threading.Event()
    stop_event.set()
    manager.task_stop_events["t1"] = stop_event
    cancelled = []
    fake_store = SimpleNamespace(
        mark_running=lambda *args, **kwargs: None,
        request_cancel=lambda task_id: cancelled.append(task_id),
    )
    monkeypatch.setattr(runtime_module, "get_runtime_state_store", lambda: fake_store)

    result = manager._mark_task_running(
        "t1",
        logging.getLogger("test"),
        None,
        "start",
    )

    assert result is None
    assert cancelled == ["t1"]
