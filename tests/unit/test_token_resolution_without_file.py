"""任务 Token 解析不再依赖 token_file，且新任务必须落到 token_id。"""
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

    def list_active_entities(self, task_type=None):
        return [RemoteRecord(row) for row in self.rows if row.get("is_active")]

    def commit(self):
        pass

    def flush(self):
        pass


def _service(monkeypatch):
    repo = _FakeTokenRepo(
        [
            {
                "id": 1,
                "name": "token-a",
                "task_type": "google_sheet",
                "is_active": True,
                "max_usage_count": 0,
                "current_in_use_count": 0,
                "task_usage_count": 0,
                "token_context": "{}",
                "token_file": "data/token.json",
            }
        ]
    )
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    monkeypatch.setattr(
        service,
        "_build_live_usage_snapshot",
        lambda: {"token_usage": {}, "current_total": 0},
    )
    monkeypatch.setattr(service, "_assert_global_usage_available", lambda *args, **kwargs: None)
    return service


def test_prepare_task_config_drops_token_file_without_forcing_token(monkeypatch):
    service = _service(monkeypatch)

    resolved = service.prepare_task_config(
        {"token_type": "file", "token_file": "data/token.json"}
    )

    assert "token_file" not in resolved
    assert "token_id" not in resolved


def test_prepare_task_config_resolves_explicit_token(monkeypatch):
    service = _service(monkeypatch)

    resolved = service.prepare_task_config(
        {"token_type": "file", "token_id": 1, "token_file": "data/token.json"}
    )

    assert resolved["token_id"] == 1
    assert resolved["token_name"] == "token-a"
    assert "token_file" not in resolved


def test_prepare_task_config_drops_inline_token_json(monkeypatch):
    service = _service(monkeypatch)

    resolved = service.prepare_task_config(
        {"token_type": "file", "token_json": '{"refresh_token": "secret"}'}
    )

    assert "token_json" not in resolved


def test_resolve_task_token_falls_back_to_first_active(monkeypatch):
    service = _service(monkeypatch)

    token = service.resolve_task_token({})

    assert token.id == 1
    assert token.name == "token-a"
