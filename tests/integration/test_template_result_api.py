"""模板 / 任务结果接口集成测试（B1 归位后统一信封契约锁定）。

- /api/templates CRUD 走 task_template_repository；
- /api/results* 自 template_api 归位到 result_api（URL 不变）；
- 全部响应为统一信封 {status, code, message, data}。
"""
import secrets

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Task, TaskResult, User

# 随机测试口令：仅本模块 fixture 使用，不落任何真实凭据字面量。
TEST_PASSWORD = secrets.token_hex(16)


def _create_user(app, username):
    with app.app_context():
        user = User(
            username=username,
            password_hash=generate_password_hash(TEST_PASSWORD),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, username):
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_client(app_factory):
    app = app_factory
    _create_user(app, "tpl_user")
    client = app.test_client()
    token = _login(client, "tpl_user")
    return client, _auth(token)


def test_template_crud_envelope(auth_client):
    client, headers = auth_client

    # CREATE
    resp = client.post(
        "/api/templates",
        headers=headers,
        json={"name": "tpl-a", "description": "d", "config": {"task_type": "google_sheet"}},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success" and body["code"] == 0
    assert body["data"]["template"]["name"] == "tpl-a"
    template_id = body["data"]["template"]["id"]

    # LIST（含 task_type 过滤：解析 config 后按 config.task_type 过滤）
    resp = client.get("/api/templates", headers=headers)
    body = resp.get_json()
    assert [t["name"] for t in body["data"]["templates"]] == ["tpl-a"]
    resp = client.get("/api/templates?task_type=google_sheet_C4", headers=headers)
    assert resp.get_json()["data"]["templates"] == []

    # DETAIL
    resp = client.get(f"/api/templates/{template_id}", headers=headers)
    assert resp.get_json()["data"]["id"] == template_id

    # UPDATE
    resp = client.put(
        f"/api/templates/{template_id}",
        headers=headers,
        json={"name": "tpl-b", "config": {"task_type": "google_sheet"}},
    )
    assert resp.get_json()["data"]["template"]["name"] == "tpl-b"

    # DELETE + 二次删除 404 信封
    resp = client.delete(f"/api/templates/{template_id}", headers=headers)
    assert resp.get_json()["message"] == "模板已删除"
    resp = client.delete(f"/api/templates/{template_id}", headers=headers)
    assert resp.status_code == 404
    body = resp.get_json()
    assert body == {"status": "error", "code": 404, "message": "模板不存在", "data": None}


def test_results_endpoints_envelope(auth_client):
    client, headers = auth_client

    # 空列表
    resp = client.get("/api/results", headers=headers)
    assert resp.get_json()["data"] == {
        "results": [], "total": 0, "pages": 0, "current_page": 1,
    }

    # 准备任务与结果
    with client.application.app_context():
        task = Task(id="t-r1", name="result task", status="completed")
        db.session.add(task)
        db.session.commit()
        result = TaskResult(task_id="t-r1", step_index=1, success=True)
        db.session.add(result)
        db.session.commit()
        result_id = result.id

    # 列表：精简投影键不变，整体移入 data
    resp = client.get("/api/results", headers=headers)
    body = resp.get_json()["data"]
    assert body["total"] == 1
    assert set(body["results"][0].keys()) == {
        "id", "task_id", "step_index", "success", "timestamp",
    }

    # 按 task_id 过滤：任务不存在返回空页
    resp = client.get("/api/results?task_id=missing", headers=headers)
    assert resp.get_json()["data"]["total"] == 0

    # 详情：data 内含 task_type
    resp = client.get(f"/api/results/{result_id}", headers=headers)
    body = resp.get_json()
    assert body["data"]["id"] == result_id
    assert body["data"]["task_type"] == "google_sheet"

    # 删除 + 二次删除 404
    resp = client.delete(f"/api/results/{result_id}", headers=headers)
    assert resp.get_json()["message"] == "结果已删除"
    resp = client.delete(f"/api/results/{result_id}", headers=headers)
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "结果不存在"
