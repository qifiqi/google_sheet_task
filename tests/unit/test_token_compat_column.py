"""token_file 本地列删除后，HTTP 写入仍需给远端兼容唯一占位值。"""
from types import SimpleNamespace

from app.models import GoogleSheetToken
from app.repositories.http_backend.google_sheet_token_repository import (
    GoogleSheetTokenHttpRepository,
)


def test_model_no_longer_has_token_file_column():
    assert "token_file" not in GoogleSheetToken.__table__.columns


class _FakeTokenController:
    def __init__(self):
        self.payloads = []

    def modify_or_add(self, payload):
        self.payloads.append(payload)
        return "1"


def test_http_add_entity_sends_unique_legacy_token_file_for_remote_compat():
    controller = _FakeTokenController()
    repo = GoogleSheetTokenHttpRepository(
        api=SimpleNamespace(param_google_sheet_tokens=controller)
    )
    entity = SimpleNamespace(
        id=None,
        to_dict=lambda: {
            "name": "token-a",
            "task_type": "google_sheet",
            "token_context": "{}",
            "is_active": True,
        },
    )

    repo.add_entity(entity)

    payload = controller.payloads[0]
    assert payload["token_file"].startswith("legacy-token:")
