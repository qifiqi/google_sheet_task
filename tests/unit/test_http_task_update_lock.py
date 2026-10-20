"""HTTP 任务 update_fields 的读改写必须进入任务级仲裁锁。"""
from contextlib import contextmanager
from types import SimpleNamespace

from app.adjudication import configure_arbiter
from app.repositories.http_backend.task_repository import TaskHttpRepository


class _FakeArbiter:
    def __init__(self):
        self.names = []

    @contextmanager
    def mutex(self, name, ttl_seconds=15, wait_seconds=5.0):
        self.names.append(name)
        yield True


class _FakeTasksApi:
    def __init__(self):
        self.saved = []

    def get_info_by_id(self, payload):
        return {
            "id": payload["id"],
            "name": "t1",
            "task_type": "google_sheet",
            "status": "running",
            "config": "{}",
        }

    def modify_or_add(self, payload):
        self.saved.append(payload)
        return dict(payload)


def test_update_fields_uses_task_state_mutex():
    arbiter = _FakeArbiter()
    configure_arbiter(arbiter)
    try:
        api = SimpleNamespace(param_tasks=_FakeTasksApi())
        repo = TaskHttpRepository(api=api)

        updated = repo.update_fields("t1", status="cancelled")

        assert updated["status"] == "cancelled"
        assert arbiter.names == ["task:t1:state"]
    finally:
        configure_arbiter(None)
