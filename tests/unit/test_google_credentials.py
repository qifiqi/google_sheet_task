"""Google Sheet 凭据从 Token JSON 内存构造，不依赖落盘文件。"""
import json

import pytest
from google.oauth2.credentials import Credentials

from app.services.google_sheet_client import (
    GOOGLE_SHEET_SCOPES,
    build_google_credentials,
)


def test_build_authorized_user_credentials_from_json():
    context = json.dumps(
        {
            "type": "authorized_user",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "refresh_token": "refresh-token",
        }
    )

    credentials = build_google_credentials(context)

    assert isinstance(credentials, Credentials)
    assert credentials.refresh_token == "refresh-token"
    assert list(credentials.scopes) == GOOGLE_SHEET_SCOPES


def test_build_credentials_rejects_empty_context():
    with pytest.raises(ValueError):
        build_google_credentials("")
