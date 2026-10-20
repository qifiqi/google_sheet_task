"""HTTP 任务结果仓储的实体契约：属性访问链必须拿到 RemoteRecord。"""
from types import SimpleNamespace

from app.repositories.http_backend.base import RemoteRecord
from app.repositories.http_backend.task_result_repository import (
    TaskResultHttpRepository,
)


_RESULT_ROW = {
    "id": 1,
    "task_id": "t1",
    "step_index": 0,
    "success": 1,
    "result": "{}",
    "parameters": "{}",
    "timestamp": "2026-01-01T00:00:00",
}


class _FakeResultsApi:
    def get_info_by_id(self, payload):
        return dict(_RESULT_ROW, id=payload["id"])

    def get_data_by_page_list(self, payload):
        return [dict(_RESULT_ROW)], 1


def _repo():
    api = SimpleNamespace(param_task_results=_FakeResultsApi())
    return TaskResultHttpRepository(api=api)


def test_get_entity_returns_remote_record_with_attribute_access():
    result = _repo().get_entity(1)

    assert isinstance(result, RemoteRecord)
    assert result.task_id == "t1"
    assert result.success is True


def test_get_export_entity_returns_remote_record():
    result = _repo().get_export_entity(1)

    assert isinstance(result, RemoteRecord)
    assert result.task_id == "t1"


def test_list_entities_by_task_ordered_returns_remote_records():
    rows = _repo().list_entities_by_task_ordered("t1")

    assert rows and isinstance(rows[0], RemoteRecord)
    assert rows[0].success is True
