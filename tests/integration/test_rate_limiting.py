"""保护性限流行为验证（docs/design/api-model-query-audit/06）。

TestingConfig 默认 RATELIMIT_ENABLED=False；本用例显式打开限流，
验证超限请求返回 429 中文信封、键按用户隔离。
"""

import uuid

from app.extensions import limiter
from app.utils.api_response import success


def test_rate_limit_exceeded_returns_429_chinese_envelope(app_factory):
    app = app_factory
    app.config.update(RATELIMIT_ENABLED=True)
    # 共享 limiter 单例的 enabled 被 TestingConfig（False）的 init_app 锁定，
    # 本用例显式重开；后续 app 的 init_app 会按各自配置恢复。
    limiter.enabled = True

    def _probe():
        return success(data={"ok": True})

    # 已注册蓝图不能再 add route；用 add_url_rule + 装饰器等价挂载探针。
    # 键用本次运行唯一值：limiter 的 memory 存储进程内共享，防止套件内键污染。
    probe_key = f"probe-{uuid.uuid4().hex}"
    limited = limiter.limit("2/minute", key_func=lambda: probe_key)(_probe)
    app.add_url_rule("/xpl/_limit_probe", view_func=limited)

    client = app.test_client()
    assert client.get("/xpl/_limit_probe").status_code == 200
    assert client.get("/xpl/_limit_probe").status_code == 200

    resp = client.get("/xpl/_limit_probe")
    assert resp.status_code == 429
    body = resp.get_json()
    assert body == {
        "status": "error",
        "code": 429,
        "message": "请求过于频繁，请稍后重试",
        "data": None,
    }


def test_testing_config_disables_rate_limit():
    """既有集成测试约定：TestingConfig 下限流关闭，轮询路径不受影响。"""
    from app.config import TestingConfig

    assert TestingConfig.RATELIMIT_ENABLED is False

def test_export_endpoint_rate_limited_by_user(app_factory):
    """真实导出路由挂载验证：rate_limit_export（10/min，user 键）。

    限流在视图前生效——前 10 次按业务返回 404（任务不存在），
    第 11 次起 429 中文信封。
    """
    import secrets as _secrets
    from werkzeug.security import generate_password_hash

    pw = _secrets.token_hex(12)
    app = app_factory
    app.config.update(RATELIMIT_ENABLED=True)
    limiter.enabled = True

    with app.app_context():
        from app.extensions import db
        from app.models import User
        db.create_all()
        db.session.add(User(username="exporter", password_hash=generate_password_hash(pw), is_active=True))
        db.session.commit()

    client = app.test_client()
    r = client.post("/api/auth/login", json={"username": "exporter", "password": pw})
    headers = {"Authorization": "Bearer " + r.get_json()["data"]["access_token"]}

    codes = [
        client.get("/api/exports/tasks/nonexistent", headers=headers).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [404] * 10
    assert codes[10] == 429
    body = client.get("/api/exports/tasks/nonexistent", headers=headers).get_json()
    assert body["status"] == "error" and body["code"] == 429
    assert body["message"] == "请求过于频繁，请稍后重试"

