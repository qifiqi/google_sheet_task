from app.models import Task, db
from app.routes import api_task_routes


def _create_task(task_id: str, task_type: str = "google_sheet") -> Task:
    """创建测试任务，供接口回归用例复用。"""
    task = Task(
        id=task_id,
        name="测试任务",
        description="测试描述",
        status="pending",
        task_type=task_type,
        config='{"spreadsheet_id":"sheet-1","sheet_name":"Sheet1","parameters":[["a"]]}',
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_get_task_detail_returns_task_payload(client, monkeypatch):
    """任务详情接口应直接返回任务查询结果。"""
    expected_task = {"id": "task-001", "status": "running", "name": "演示任务"}

    monkeypatch.setattr(
        api_task_routes.task_manager,
        "get_task_status",
        lambda task_id: expected_task if task_id == "task-001" else None,
    )

    response = client.get("/api/tasks/task-001")

    assert response.status_code == 200
    assert response.get_json() == {"status": "success", "task": expected_task}


def test_update_task_config_normalizes_c4_payload(client, app, monkeypatch):
    """更新配置接口应先按任务类型归一化，再把结果交给 TaskManager。"""
    with app.app_context():
        _create_task("task-c4", task_type="google_sheet_C4")

    captured = {}

    def fake_update_task_config(task_id, new_config, name, description):
        captured["task_id"] = task_id
        captured["new_config"] = new_config
        captured["name"] = name
        captured["description"] = description
        return {"status": "success", "message": "更新成功"}

    monkeypatch.setattr(api_task_routes.task_manager, "update_task_config", fake_update_task_config)

    response = client.put(
        "/api/tasks/task-c4/config",
        json={
            "name": "新的任务名",
            "description": "新的说明",
            "config": {
                "token_type": "file",
                "token_file": "data/token.json",
                "spreadsheet_id": "sheet-c4",
                "sheet_name": "SheetC4",
                "parameters": [["000001"]],
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert captured["task_id"] == "task-c4"
    assert captured["name"] == "新的任务名"
    assert captured["description"] == "新的说明"
    assert captured["new_config"]["task_type"] == "google_sheet_C4"
    assert captured["new_config"]["sheets"] == [
        {"spreadsheet_id": "sheet-c4", "sheet_name": "SheetC4", "title": ""}
    ]
    assert captured["new_config"]["parameters"] == [["000001"]]


def test_restart_task_returns_400_when_manager_rejects(client, monkeypatch):
    """重启任务接口在业务拒绝时应返回 400。"""
    monkeypatch.setattr(
        api_task_routes.task_manager,
        "restart_task",
        lambda task_id, resume_from_checkpoint: {
            "status": "error",
            "message": "当前状态不允许重启",
        },
    )

    response = client.post("/api/tasks/task-002/restart", json={"resume_from_checkpoint": False})

    assert response.status_code == 400
    assert response.get_json()["message"] == "当前状态不允许重启"


def test_create_restart_task_starts_new_task(client, monkeypatch):
    """创建重启任务接口应在创建成功后继续触发启动。"""
    monkeypatch.setattr(api_task_routes.task_manager, "create_restart_task", lambda task_id: "task-003-restart")
    monkeypatch.setattr(api_task_routes.task_manager, "start_task", lambda task_id: task_id == "task-003-restart")

    response = client.post("/api/tasks/task-003/create-restart")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "success",
        "new_task_id": "task-003-restart",
        "message": "重启任务创建并启动成功",
    }
