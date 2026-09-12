"""Google Sheet 配置表 API 回归测试。

回归守卫：B3 重构（ad37db0）误删了路由内 GoogleSheetTableType 的 import，
导致 GET/POST /api/google-sheets 任何请求都在 _normalize_table_type 处
抛 NameError → 500 信封。本文件保证该端点可达且 table_type 归一化生效。
"""

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User


def _create_user(app, username, password="secret123"):
    with app.app_context():
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, username, password="secret123"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]["access_token"]


def _auth_client(app_factory):
    app = app_factory
    _create_user(app, "sheet_admin")
    client = app.test_client()
    token = _login(client, "sheet_admin")
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client


class TestGoogleSheetsEndpoint:
    def test_list_sheets_success_envelope(self, app_factory):
        client = _auth_client(app_factory)

        resp = client.get("/api/google-sheets")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["code"] == 0
        assert body["data"]["items"] == []

    def test_table_type_normalized(self, app_factory):
        client = _auth_client(app_factory)

        # c31 归一化为 c3；非法值归一化为 None，都不应 500
        for raw in ("c31", "not-a-type", ""):
            resp = client.get(f"/api/google-sheets?table_type={raw}")
            assert resp.status_code == 200, resp.get_data(as_text=True)
            assert resp.get_json()["status"] == "success"
