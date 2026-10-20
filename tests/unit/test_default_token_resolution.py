"""默认 Token 解析：任务 token_id > default_token_id > 首个可用 Token。"""
from app.repositories.http_backend.base import RemoteRecord
from app.services import google_sheet_token_service as token_service_module


class _FakeTokenRepo:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def get_entity(self, token_id):
        for row in self.rows:
            if int(row["id"]) == int(token_id):
                return RemoteRecord(row)
        return None

    def list_entities_ordered(self, task_type=None):
        return [RemoteRecord(row) for row in self.rows]

    def commit(self):
        pass

    def flush(self):
        pass


def _service(monkeypatch, default_token_id=None):
    repo = _FakeTokenRepo(
        [
            {"id": 1, "name": "first", "task_type": "google_sheet", "is_active": True},
            {"id": 2, "name": "default", "task_type": "google_sheet", "is_active": True},
        ]
    )
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(
        service, "_get_default_token_id", lambda: int(default_token_id or 0)
    )
    return service


def test_default_token_preferred_over_first_active(monkeypatch):
    service = _service(monkeypatch, default_token_id=2)

    token = service.resolve_task_token({})

    assert token.id == 2


def test_explicit_task_token_beats_default(monkeypatch):
    service = _service(monkeypatch, default_token_id=2)

    token = service.resolve_task_token({"token_id": 1})

    assert token.id == 1


def test_invalid_default_falls_back_to_first_active(monkeypatch):
    service = _service(monkeypatch, default_token_id=999)

    token = service.resolve_task_token({})

    assert token.id == 1


def test_token_json_field_removed_from_task_config_schema():
    from app.schemas.task_configs import TokenRefFields

    assert "token_json" not in TokenRefFields.model_fields
