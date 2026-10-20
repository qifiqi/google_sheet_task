"""Token 使用计数必须经仓储 update_fields 落库（HTTP 模式无 ORM 回写）。"""
from datetime import datetime

from app.repositories.http_backend.base import RemoteRecord
from app.services import google_sheet_token_service as token_service_module


class _FakeTokenRepo:
    def __init__(self, row):
        self.row = dict(row)
        self.updates = []

    def get_entity(self, token_id):
        return RemoteRecord(self.row)

    def update_fields(self, token_id, commit=True, **fields):
        self.updates.append(fields)
        self.row.update(fields)
        return dict(self.row)

    def commit(self):
        pass

    def flush(self):
        pass


def _service(monkeypatch, row):
    repo = _FakeTokenRepo(row)
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(
        service,
        "_build_live_usage_snapshot",
        lambda: {"token_usage": {1: 1}, "current_total": 1},
    )
    monkeypatch.setattr(service, "_assert_global_usage_available", lambda **kwargs: None)
    monkeypatch.setattr(service, "_assert_token_usage_available", lambda *args: None)
    return service, repo


def test_increment_usage_persists_counts(monkeypatch):
    service, repo = _service(
        monkeypatch,
        {
            "id": 1,
            "task_usage_count": 3,
            "current_in_use_count": 1,
            "last_used_at": None,
        },
    )

    token = service.increment_usage(1)

    assert repo.updates and repo.updates[0]["task_usage_count"] == 4
    assert repo.updates[0]["current_in_use_count"] == 2
    assert isinstance(repo.updates[0]["last_used_at"], datetime)
    assert token.current_in_use_count == 2


def test_release_usage_persists_count(monkeypatch):
    service, repo = _service(
        monkeypatch,
        {
            "id": 1,
            "task_usage_count": 3,
            "current_in_use_count": 2,
            "last_used_at": None,
        },
    )

    token = service.release_usage(1)

    assert repo.updates == [
        {
            "current_in_use_count": 1,
            "last_used_at": repo.updates[0]["last_used_at"],
        }
    ]
    assert isinstance(repo.updates[0]["last_used_at"], datetime)
    assert token.current_in_use_count == 1
