"""内部命令端点：共享密钥鉴权 + 委托 Web TaskManager。"""
import tempfile
from pathlib import Path

from app import create_app


def _app(monkeypatch, secret):
    monkeypatch.setenv("INTERNAL_COMMAND_SECRET", secret)
    # SQLite 本地回退已移除（config 重构）：测试显式给临时库地址。
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{Path(tempfile.mkdtemp()) / 'test_internal_cmd.db'}",
    )
    app = create_app()
    app.config.update(TESTING=True)
    return app


def test_endpoint_disabled_without_secret(monkeypatch):
    app = _app(monkeypatch, "")

    with app.test_client() as client:
        response = client.post(
            "/api/internal/task-command",
            json={"action": "restart", "task_id": "t1"},
        )

    assert response.status_code == 404


def test_endpoint_rejects_wrong_secret(monkeypatch):
    app = _app(monkeypatch, "test-secret")

    with app.test_client() as client:
        response = client.post(
            "/api/internal/task-command",
            json={"action": "restart", "task_id": "t1"},
            headers={"X-Internal-Secret": "wrong"},
        )

    assert response.status_code == 403


def test_endpoint_delegates_restart_to_task_manager(monkeypatch):
    app = _app(monkeypatch, "test-secret")
    import app.routes.internal_api as internal_api

    calls = {}

    class _FakeTaskManager:
        def restart_task(self, task_id, resume_from_checkpoint=True):
            calls["task_id"] = task_id
            calls["resume"] = resume_from_checkpoint
            return {"message": "任务重启成功", "restart_from_step": 3}

    monkeypatch.setattr(internal_api, "task_manager", _FakeTaskManager())

    with app.test_client() as client:
        response = client.post(
            "/api/internal/task-command",
            json={
                "action": "restart",
                "task_id": "t1",
                "resume_from_checkpoint": False,
            },
            headers={"X-Internal-Secret": "test-secret"},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["data"]["restart_from_step"] == 3
    assert calls == {"task_id": "t1", "resume": False}
