"""Token 外部输出契约：列表不下发完整上下文，详情返回脱敏预览，编辑回显不覆盖真值。"""
import json

from app.repositories.http_backend.base import RemoteRecord
from app.services import google_sheet_token_service as token_service_module
from app.utils.secret_masking import mask_token_context


FULL_CONTEXT = json.dumps(
    {
        "type": "authorized_user",
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "CLIENT-SECRET-VALUE",
        "refresh_token": "REFRESH-TOKEN-VALUE",
    }
)


class _FakeTokenRepo:
    def __init__(self):
        self.row = {
            "id": 1,
            "name": "token-a",
            "task_type": "google_sheet",
            "token_file": "data/token-1.json",
            "token_context": FULL_CONTEXT,
            "max_usage_count": 2,
            "current_in_use_count": 1,
            "task_usage_count": 3,
            "is_active": True,
            "last_used_at": "2026-10-20T10:00:00",
            "created_at": "2026-10-01T10:00:00",
            "updated_at": "2026-10-20T10:00:00",
        }
        self.updates = []

    def list_entities_ordered(self, task_type=None):
        return [RemoteRecord(self.row)]

    def get_entity(self, token_id):
        return RemoteRecord(self.row)

    def update_fields(self, token_id, commit=True, **fields):
        self.updates.append(fields)
        self.row.update(fields)
        return dict(self.row)

    def flush(self):
        pass

    def commit(self):
        pass


def _service(monkeypatch):
    repo = _FakeTokenRepo()
    monkeypatch.setattr(token_service_module, "google_sheet_token_repository", repo)
    service = token_service_module.GoogleSheetTokenService()
    service.ensure_token_file = lambda token: token.token_file
    return service, repo


def test_list_tokens_does_not_expose_full_context(monkeypatch):
    service, _ = _service(monkeypatch)

    tokens = service.list_tokens()

    assert "token_context" not in tokens[0]
    assert tokens[0]["token_context_size"] == len(FULL_CONTEXT)


def test_get_token_with_context_returns_masked_preview(monkeypatch):
    service, _ = _service(monkeypatch)

    token = service.get_token(1, include_context=True)

    assert "CLIENT-SECRET-VALUE" not in token["token_context"]
    assert "REFRESH-TOKEN-VALUE" not in token["token_context"]
    assert token["token_context"] == mask_token_context(FULL_CONTEXT)


def test_update_token_ignores_masked_echo(monkeypatch):
    service, repo = _service(monkeypatch)

    service.update_token(1, name="renamed", token_context=mask_token_context(FULL_CONTEXT))

    assert repo.updates == [{"name": "renamed"}]
    assert repo.row["token_context"] == FULL_CONTEXT
