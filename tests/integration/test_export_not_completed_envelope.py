"""导出端点"任务未完成"拒绝路径回归。

覆盖 GET /api/exports/tasks/<id> 与 /tasks/<id>/stocks（C7/C1_1 详情页按股票代码导出）：
- 非 completed 任务返回 400 统一信封，message 带任务名与"尚未完成"；
- 防回归：BadRequestError 只接受 message/code/http_status/detail/log_level，
  历史上误传 data= 会在 raise 构造阶段抛 TypeError，被全局兜底转成 500「服务器内部错误」，
  真实业务原因被吞掉。
"""
import pytest

from app.exceptions import BadRequestError
from app.models import Task, db


@pytest.fixture()
def client(app_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    return app_factory.test_client()


def _add_task(task_id, status):
    db.session.add(Task(
        id=task_id,
        name="随机K线校验任务",
        task_type="google_sheet_c7",
        status=status,
        config="{}",
    ))
    db.session.commit()


@pytest.mark.parametrize("suffix", ["", "/stocks"])
def test_not_completed_task_export_returns_400_envelope(app_factory, client, suffix):
    with app_factory.app_context():
        _add_task("task-pending", "pending")

    resp = client.get(f"/api/exports/tasks/task-pending{suffix}")

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["code"] == 400
    assert "尚未完成" in body["message"]
    assert "随机K线校验任务" in body["message"]


def test_app_exception_preserves_structured_data():
    """异常体系 data 通道：结构化错误上下文随信封 data 下发（本分支契约）。"""
    from app.exceptions import BadRequestError

    exc = BadRequestError("任务尚未完成", data={"task_id": "t1", "task_status": "running"})
    assert exc.data == {"task_id": "t1", "task_status": "running"}
