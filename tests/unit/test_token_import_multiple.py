"""Token 去文件化后，连续导入多个 Token 不应触发 token_file 唯一冲突。"""
import json

from app.services.google_sheet_token_service import GoogleSheetTokenService


def _context(client_id):
    return json.dumps(
        {
            "type": "authorized_user",
            "client_id": client_id,
            "client_secret": "client-secret",
            "refresh_token": "refresh-token",
        }
    )


def test_import_two_tokens_uses_unique_legacy_identifier(app_factory):
    service = GoogleSheetTokenService()

    first, first_is_new = service.import_token(
        token_context=_context("client-1"), name="one"
    )
    second, second_is_new = service.import_token(
        token_context=_context("client-2"), name="two"
    )

    assert first_is_new is True
    assert second_is_new is True
    assert first["id"] != second["id"]
