"""JWT 令牌生命周期回归测试。

覆盖修复后的行为约定：
- 登录不递增 token_version：同一账号多端登录互不挤下线；
- refresh 轮换 refresh_token（滑动续期），新 refresh 可用；
- 修改密码吊销所有存量会话（含当前会话）；
- 管理员重置密码吊销目标用户的所有会话；
- JWT 密钥优先取环境变量（与启动校验同源）。
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


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _me(client, token):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_login_keeps_existing_sessions_valid(app_factory):
    app = app_factory
    _create_user(app, "multi_device")

    client = app.test_client()
    first = _login(client, "multi_device", "secret123")
    second = _login(client, "multi_device", "secret123")

    # 第二次登录后，第一端的 access 与 refresh 仍可用（不再互踢）
    assert _me(client, first["access_token"]).status_code == 200
    refreshed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert refreshed.status_code == 200


def test_refresh_rotates_refresh_token(app_factory):
    app = app_factory
    _create_user(app, "rotating")
    client = app.test_client()
    data = _login(client, "rotating", "secret123")

    resp = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200
    payload = resp.get_json()["data"]
    assert payload["refresh_token"], "refresh 响应必须携带新的 refresh_token"

    # 轮换出的新 refresh_token 可继续换新 access_token（滑动续期闭环）
    second = client.post("/api/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert second.status_code == 200
    assert _me(client, second.get_json()["data"]["access_token"]).status_code == 200


def test_change_password_revokes_all_sessions(app_factory):
    app = app_factory
    _create_user(app, "changer")
    client = app.test_client()
    data = _login(client, "changer", "secret123")

    resp = client.put(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {data['access_token']}"},
        json={"old_password": "secret123", "new_password": "newpass456"},
    )
    assert resp.status_code == 200

    # 改密后旧 access 失效、旧 refresh 也失效
    assert _me(client, data["access_token"]).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    ).status_code == 401

    # 新密码可重新登录
    assert client.post(
        "/api/auth/login",
        json={"username": "changer", "password": "newpass456"},
    ).status_code == 200


def test_admin_password_reset_revokes_sessions(app_factory):
    app = app_factory
    target_id = _create_user(app, "target")
    _create_user(app, "operator")
    client = app.test_client()
    operator = _login(client, "operator", "secret123")
    target = _login(client, "target", "secret123")

    resp = client.put(
        f"/api/admin/users/{target_id}",
        headers={"Authorization": f"Bearer {operator['access_token']}"},
        json={"password": "resetpwd789"},
    )
    assert resp.status_code == 200

    # 被重置用户的旧令牌全部失效
    assert _me(client, target["access_token"]).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": target["refresh_token"]},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "target", "password": "resetpwd789"},
    ).status_code == 200


def test_get_secret_prefers_environment(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        from app.utils.auth import DEFAULT_JWT_SECRET, _get_secret

        monkeypatch.setenv("JWT_SECRET_KEY", "env-secret-value")
        assert _get_secret() == "env-secret-value"

        monkeypatch.delenv("JWT_SECRET_KEY")
        # 测试库的 system_configs 无该配置项，回退默认值
        assert _get_secret() == DEFAULT_JWT_SECRET
