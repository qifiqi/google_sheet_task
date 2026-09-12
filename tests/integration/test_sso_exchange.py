"""主服务 SSO 换票集成测试（docs/design/sso-integration-2026-09/）。

覆盖：首次建号挂默认角色、同名合并保留既有角色、禁用账号拒绝、上游无效
令牌/超时/HTTP 错误映射、缺 Token 头、重复换票幂等、SSO 开关、SSRF 地址
校验，以及 init_rbac 对默认角色的幂等播种与权限并集补齐。
"""

import pytest
import requests

from app.extensions import db
from app.models import Permission, Role, User
from app.startup import init_rbac

SSO_EXCHANGE = "/api/auth/sso/exchange"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _mock_main_service(monkeypatch, *, status_code=200, payload=None, text="", exc=None):
    """绕过真实 DNS/网络：域名解析固定到公网 IP，requests.post 返回/抛出给定结果。"""
    monkeypatch.setattr(
        "app.services.sso_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    def _fake_post(url, **kwargs):
        if exc is not None:
            raise exc
        return _FakeResponse(status_code=status_code, payload=payload, text=text)

    monkeypatch.setattr("app.services.sso_service.requests.post", _fake_post)


def _ok_payload(username="sso_user", userid=1):
    return {
        "ret_code": 200,
        "ret_msg": "请求(或处理)成功",
        "ret_obj": {"userid": userid, "username": username},
    }


def _seed_rbac(app):
    with app.app_context():
        init_rbac()


def _exchange(client, token="main-token"):
    return client.post(SSO_EXCHANGE, headers={"Token": token})


def _me(client, access_token):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})


def _create_local_user(username, *, role_code=None, is_active=True):
    user = User(
        username=username,
        password_hash="not-a-real-hash",
        is_active=is_active,
    )
    if role_code:
        role = Role.query.filter_by(code=role_code).first()
        if role is None:
            role = Role(name=role_code, code=role_code)
            db.session.add(role)
        user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user.id


def test_first_exchange_provisions_user_with_default_role(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, payload=_ok_payload(username="sso_new_user", userid=280566))

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["access_token"] and data["refresh_token"]

    me = _me(client, data["access_token"])
    assert me.status_code == 200
    user = me.get_json()["data"]
    assert user["username"] == "sso_new_user"
    assert "main_service_user" in [role["code"] for role in user["roles"]]
    # 默认权限开放业务模块，但不越权到系统模块
    assert "page:google_sheet:c3" in user["permissions"]
    assert "page:backtest:list" in user["permissions"]
    assert "page:admin:users" not in user["permissions"]


def test_exchange_merges_existing_user_roles(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _create_local_user("fuqing", role_code="admin")
    _mock_main_service(monkeypatch, payload=_ok_payload(username="fuqing"))

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 200
    user = resp.get_json()["data"]["user"]
    role_codes = [role["code"] for role in user["roles"]]
    # 同名合并策略 A：保留既有 admin 角色，仅追加默认角色
    assert "admin" in role_codes
    assert "main_service_user" in role_codes


def test_exchange_rejects_disabled_user(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _create_local_user("frozen_user", is_active=False)
    _mock_main_service(monkeypatch, payload=_ok_payload(username="frozen_user"))

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 401
    assert "禁用" in resp.get_json()["message"]


def test_exchange_rejects_upstream_invalid_token(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, payload={"ret_code": 500, "ret_msg": "token invalid", "ret_obj": None})

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 401


def test_exchange_maps_upstream_timeout_to_service_error(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, exc=requests.Timeout("connect timeout"))

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 500
    assert "超时" in resp.get_json()["message"]


def test_exchange_maps_upstream_http_error_to_service_error(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, status_code=502)

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 500


def test_exchange_requires_token_header(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, payload=_ok_payload())

    client = app.test_client()
    resp = client.post(SSO_EXCHANGE)
    assert resp.status_code == 401


def test_exchange_is_idempotent(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    _mock_main_service(monkeypatch, payload=_ok_payload(username="repeat_user"))

    client = app.test_client()
    first = _exchange(client)
    second = _exchange(client)
    assert first.status_code == second.status_code == 200

    with app.app_context():
        user = User.query.filter_by(username="repeat_user").one()
        assert [role.code for role in user.roles] == ["main_service_user"]


def test_exchange_respects_sso_enabled_switch(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    app.config["SSO_ENABLED"] = False
    _mock_main_service(monkeypatch, payload=_ok_payload())

    client = app.test_client()
    resp = _exchange(client)
    assert resp.status_code == 500
    assert "未启用" in resp.get_json()["message"]


def test_exchange_rejects_non_https_and_private_verify_url(app_factory, monkeypatch):
    app = app_factory
    _seed_rbac(app)
    client = app.test_client()

    # 非 HTTPS：直接拒绝，不发请求
    app.config["SSO_MAIN_VERIFY_URL"] = "http://127.0.0.1:9999/api/SysUser/GetUserInfo"
    resp = _exchange(client)
    assert resp.status_code == 500
    assert "https" in resp.get_json()["message"]

    # HTTPS 但解析为私网地址：拒绝
    app.config["SSO_MAIN_VERIFY_URL"] = "https://intranet.example.com/api/SysUser/GetUserInfo"
    monkeypatch.setattr(
        "app.services.sso_service.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("192.168.1.10", 443))],
    )
    resp = _exchange(client)
    assert resp.status_code == 500


def test_init_rbac_seeds_sso_role_with_union_permissions(app_factory):
    app = app_factory
    with app.app_context():
        init_rbac()
        role = Role.query.filter_by(code="main_service_user").one()
        codes = {perm.code for perm in role.permissions}
        assert "page:google_sheet:c3" in codes
        assert "page:global_preview:single_product" in codes
        assert "page:admin:dashboard" in codes

        # 管理员后台手工追加的权限不被下次启动覆盖（并集语义）
        extra = Permission.query.filter_by(code="page:admin:logs").one()
        role.permissions = list(role.permissions) + [extra]
        db.session.commit()

        init_rbac()
        refreshed = Role.query.filter_by(code="main_service_user").one()
        refreshed_codes = [perm.code for perm in refreshed.permissions]
        assert "page:admin:logs" in refreshed_codes
        assert refreshed_codes.count("page:google_sheet:c3") == 1


@pytest.mark.usefixtures()
def test_local_password_login_still_works_alongside_sso(app_factory):
    app = app_factory
    _seed_rbac(app)
    client = app.test_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["username"] == "admin"
