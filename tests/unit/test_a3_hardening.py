"""A3 批次（BUG-10 ~ BUG-17）修复验收测试。

对应 docs/design/code-audit-2026-09/01-bugs-and-fixes.md 各"验收标准"。
"""
import json
from datetime import datetime

import pytest

from app.exceptions import ForbiddenError, UnauthorizedError
from app.extensions import db
from app.models import SystemConfig, Task, User
from app.services.config_manager import (
    _deserialize_config_value,
    get_config_manager,
    mask_config_value,
)
from app.utils.auth import create_access_token
from app.utils.task_types import normalize_task_type


def _create_user(app, username, *, admin=False):
    """构造测试用户（密码哈希使用无效占位，登录路径由 JWT 直接构造）。"""
    with app.app_context():
        from app.models import Role

        user = User(
            username=username,
            password_hash="x",
            is_active=True,
        )
        if admin:
            role = db.session.query(Role).filter_by(code="admin").first()
            if role is None:
                role = Role(code="admin", name="管理员")
                db.session.add(role)
            user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        return user.id


def _auth_headers(user_id):
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# BUG-10 config_manager 类型往返
# ---------------------------------------------------------------------------

def test_config_set_get_refresh_type_stable(app_factory):
    """set → get → refresh → get 四步类型恒定（bool/数字/容器/None）。"""
    app = app_factory
    with app.app_context():
        cm = get_config_manager()
        cases = {
            "audit_bool_key": True,
            "audit_int_key": 42,
            "audit_list_key": [1, 2, 3],
            "audit_none_key": None,
            "audit_str_key": "plain-text",
        }
        try:
            for key, value in cases.items():
                assert cm.set_config(key, value) is True
                assert cm.get_config(key) == value
                cm.refresh_cache()
                refreshed = cm.get_config(key)
                assert refreshed == value, f"{key} 值漂移"
                assert type(refreshed) is type(value), f"{key} 类型漂移: {type(refreshed)} vs {type(value)}"
        finally:
            for key in cases:
                cm.delete_config(key)


def test_config_deserialize_rejects_nan_and_stays_string():
    """NaN/Infinity 不得被解析为 float；普通文本不得被静默转型。"""
    assert _deserialize_config_value("NaN") == "NaN"
    assert _deserialize_config_value("Infinity") == "Infinity"
    # 容器内的 NaN 常量同样拒绝，按原字符串返回
    assert _deserialize_config_value("[NaN, 1]") == "[NaN, 1]"
    assert _deserialize_config_value("not-a-number") == "not-a-number"
    assert _deserialize_config_value("null") is None
    assert _deserialize_config_value("true") is True
    assert _deserialize_config_value("100") == 100  # json.dumps(100) 的合法产物
    assert _deserialize_config_value("Legacy") == "Legacy"


def test_mask_config_value_masks_sensitive_keys():
    assert mask_config_value("google_sheet_token", "abc") == "***"
    assert mask_config_value("db_password", "abc") == "***"
    assert mask_config_value("max_workers", 5) == 5


def test_config_validate_endpoint_masks_plaintext(app_factory):
    """BUG-14：/api/config/validate 不得下发含敏感关键字的配置明文。"""
    app = app_factory
    with app.app_context():
        cm = get_config_manager()
        try:
            assert cm.set_config("audit_secret_probe", "plain-value") is True
            client = app.test_client()
            user_id = _create_user(app, "config-viewer")
            resp = client.get("/api/config/validate", headers=_auth_headers(user_id))
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert "plain-value" not in body
            assert "***" in body
        finally:
            cm.delete_config("audit_secret_probe")


# ---------------------------------------------------------------------------
# BUG-11 / BUG-13 / BUG-15 / BUG-17 接口行为
# ---------------------------------------------------------------------------

def test_task_to_dict_survives_corrupt_config_json(app_factory):
    """BUG-11：坏 JSON 的 Task.config 不再让 to_dict 抛异常。"""
    app = app_factory
    with app.app_context():
        task = Task(
            id="t-bad-json",
            name="bad json",
            task_type="google_sheet",
            status="pending",
            config="{not-valid-json",
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.commit()

        data = task.to_dict()
        assert data["config"] == {}


def test_admin_api_rejects_non_admin_user(app_factory):
    """BUG-17：admin CUD 端点对非管理员返回 403。"""
    app = app_factory
    with app.app_context():
        user_id = _create_user(app, "plain-user")
        client = app.test_client()
        resp = client.post(
            "/api/admin/users",
            headers=_auth_headers(user_id),
            json={"username": "victim", "password": "x", "role_ids": []},
        )
        assert resp.status_code == 403


def test_admin_api_allows_admin_user(app_factory):
    app = app_factory
    with app.app_context():
        user_id = _create_user(app, "admin-user", admin=True)
        client = app.test_client()
        resp = client.get(
            "/api/admin/users",
            headers=_auth_headers(user_id),
        )
        assert resp.status_code == 200


def test_page_redirects_anonymous_to_login(app_factory):
    """BUG-17：匿名访问管理页 302 到登录页。"""
    app = app_factory
    client = app.test_client()
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    resp2 = client.get("/backtest-training/list")
    assert resp2.status_code == 302


def test_page_accessible_with_cookie_token(app_factory):
    """页面守卫接受 cookie 回退（登录后前端写入 gsc_access_token cookie）。"""
    from app.utils.auth import ACCESS_TOKEN_COOKIE

    app = app_factory
    with app.app_context():
        user_id = _create_user(app, "page-user")
        client = app.test_client()
        client.set_cookie(ACCESS_TOKEN_COOKIE, create_access_token(user_id))
        resp = client.get("/performance_analysis/")
        assert resp.status_code == 200


def test_xpl_analyze_requires_login(app_factory):
    app = app_factory
    client = app.test_client()
    resp = client.post("/performance_analysis/analyze", json={"data": "2024-01-01 0.01"})
    assert resp.status_code == 401


def test_xpl_analyze_data_failure_returns_400(app_factory):
    """BUG-13：数据级失败不再用 200，返回 400 信封。"""
    app = app_factory
    with app.app_context():
        user_id = _create_user(app, "xpl-user")
        client = app.test_client()
        resp = client.post(
            "/performance_analysis/analyze",
            headers=_auth_headers(user_id),
            json={"data": "not-a-date bogus"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["status"] == "error"


def test_token_list_get_is_read_only(app_factory, monkeypatch):
    """BUG-15：GET /api/google-sheet-tokens 不再触发对账写库。"""
    app = app_factory
    with app.app_context():
        from app.services import google_sheet_token_service as token_service_module

        called = []
        monkeypatch.setattr(
            token_service_module.GoogleSheetTokenService,
            "reconcile_in_use_counts",
            lambda self: called.append(True),
        )

        user_id = _create_user(app, "token-viewer")
        client = app.test_client()
        resp = client.get("/api/google-sheet-tokens", headers=_auth_headers(user_id))
        assert resp.status_code == 200
        assert called == []


# ---------------------------------------------------------------------------
# BUG-16 dashboard 语义诚实化
# ---------------------------------------------------------------------------

def test_dashboard_query_lists_all_types_without_fake_permission_args():
    from app.services.task.dashboard_query import TaskDashboardQueryService

    service = TaskDashboardQueryService()
    assert not hasattr(service, "get_allowed_task_types")
    assert hasattr(service, "list_all_task_types")


# ---------------------------------------------------------------------------
# CLN-10 / CLN-11 回归锚点
# ---------------------------------------------------------------------------

def test_database_utils_only_exports_transaction_required():
    import app.utils.database as database_utils

    for dead in ("safe_delete", "safe_update", "safe_create", "DatabaseManager"):
        assert not hasattr(database_utils, dead), f"{dead} 应已删除"
    assert hasattr(database_utils, "transaction_required")


def test_no_logging_getlogger_module_loggers_outside_whitelist():
    """CLN-11：白名单外不得再用裸 logging.getLogger 做模块 logger。

    白名单：task_watchdog（专用轮转文件 handler）、app/__init__（关闭
    sqlalchemy.engine 第三方日志的开关控制）。
    """
    import pathlib
    import re

    pattern = re.compile(r"logging\.getLogger\(")
    whitelist = {
        "app/services/task_watchdog.py",
        "app/__init__.py",
        "app/utils/logger.py",
    }
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if path.as_posix() in whitelist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path}:{lineno}")
    assert offenders == []
