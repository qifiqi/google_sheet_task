"""登录/登出信封与导出错误载荷回归。"""
import pytest

from app.exceptions import BadRequestError
from app.routes.export_api import _require_completed_task


def _make_auth_disabled_app(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app


def test_require_completed_task_keeps_status_in_error_data():
    with pytest.raises(BadRequestError) as exc_info:
        _require_completed_task({"id": "t1", "name": "任务", "status": "running"})

    assert exc_info.value.data == {"task_id": "t1", "task_status": "running"}


def test_logout_returns_success_and_clears_cookie(monkeypatch):
    app = _make_auth_disabled_app(monkeypatch)

    with app.test_client() as client:
        client.set_cookie("access_token", "old-token")
        response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert "access_token=;" in response.headers.get("Set-Cookie", "")


def test_login_returns_unified_envelope(monkeypatch):
    app = _make_auth_disabled_app(monkeypatch)

    import app.routes.auth_api as auth_api

    class _FakeIdentityService:
        def login(self, username, password):
            return {
                "token": "tok-1",
                "info": {"userid": 7, "username": username},
            }

    monkeypatch.setattr(
        auth_api, "get_token_identity_service", lambda: _FakeIdentityService()
    )

    with app.test_client() as client:
        response = client.post(
            "/api/auth/login", json={"username": "alice", "password": "secret"}
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["data"]["access_token"] == "tok-1"
    assert "access_token=tok-1" in response.headers.get("Set-Cookie", "")
