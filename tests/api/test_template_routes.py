import json

from app.extensions import db
from app.models import TaskTemplate


def _create_template(name: str, config: dict, description: str = "") -> int:
    """创建测试模板并返回模板 ID，避免会话脱离问题。"""
    template = TaskTemplate(
        name=name,
        description=description,
        config=json.dumps(config, ensure_ascii=False),
    )
    db.session.add(template)
    db.session.commit()
    return template.id


def test_get_templates_filters_by_normalized_task_type(client, app):
    """模板列表接口应按归一化后的 task_type 过滤历史模板。"""
    with app.app_context():
        _create_template(
            "默认模板",
            {
                "spreadsheet_id": "sheet-default",
                "sheet_name": "Sheet1",
                "parameters": [["a"]],
            },
        )
        _create_template(
            "C5 模板",
            {
                "task_type": "google_sheet_C5",
                "token_type": "file",
                "token_file": "data/token.json",
                "spreadsheet_id": "sheet-c5",
                "sheet_name": "SheetC5",
                "parameters": [["000001"], [5], [10]],
            },
        )

    response = client.get("/api/templates?task_type=google_sheet_C5")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert len(data["templates"]) == 1
    assert data["templates"][0]["name"] == "C5 模板"


def test_create_template_normalizes_c4_config(client):
    """创建模板接口应先归一化 C4 配置再入库。"""
    response = client.post(
        "/api/templates",
        json={
            "name": "C4 模板",
            "description": "用于测试模板创建",
            "config": {
                "task_type": "google_sheet_C4",
                "token_type": "file",
                "token_file": "data/token.json",
                "spreadsheet_id": "sheet-c4",
                "sheet_name": "SheetC4",
                "parameters": [["000001"]],
            },
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["template"]["config"]["task_type"] == "google_sheet_C4"
    assert data["template"]["config"]["sheets"] == [
        {"spreadsheet_id": "sheet-c4", "sheet_name": "SheetC4", "title": ""}
    ]


def test_create_template_rejects_invalid_payload(client):
    """创建模板接口在缺少 config 时应返回 400。"""
    response = client.post(
        "/api/templates",
        json={
            "name": "非法模板",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "配置信息不能为空"


def test_get_template_detail_returns_normalized_config(client, app):
    """模板详情接口应返回归一化后的配置结构。"""
    with app.app_context():
        template_id = _create_template(
            "详情模板",
            {
                "task_type": "google_sheet_C5",
                "token_type": "file",
                "token_file": "data/token.json",
                "spreadsheet_id": "sheet-detail",
                "sheet_name": "SheetDetail",
                "parameters": [["QQQ"], [1], [2]],
            },
        )

    response = client.get(f"/api/templates/{template_id}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == template_id
    assert data["config"]["task_type"] == "google_sheet_C5"
    assert data["config"]["sheets"] == [
        {"spreadsheet_id": "sheet-detail", "sheet_name": "SheetDetail", "title": ""}
    ]


def test_update_template_normalizes_config_before_save(client, app):
    """模板更新接口应先归一化配置，再返回更新后的模板。"""
    with app.app_context():
        template_id = _create_template(
            "待更新模板",
            {
                "task_type": "google_sheet_C4",
                "token_type": "file",
                "token_file": "data/token-old.json",
                "spreadsheet_id": "sheet-old",
                "sheet_name": "SheetOld",
                "parameters": [["old"]],
            },
        )

    response = client.put(
        f"/api/templates/{template_id}",
        json={
            "name": "已更新模板",
            "description": "更新后的模板说明",
            "config": {
                "task_type": "google_sheet_C4",
                "token_type": "file",
                "token_file": "data/token-new.json",
                "spreadsheet_id": "sheet-new",
                "sheet_name": "SheetNew",
                "parameters": [["000001"]],
            },
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["template"]["name"] == "已更新模板"
    assert data["template"]["description"] == "更新后的模板说明"
    assert data["template"]["config"]["task_type"] == "google_sheet_C4"
    assert data["template"]["config"]["sheets"] == [
        {"spreadsheet_id": "sheet-new", "sheet_name": "SheetNew", "title": ""}
    ]


def test_delete_template_removes_record(client, app):
    """模板删除接口应删除记录并返回成功状态。"""
    with app.app_context():
        template_id = _create_template(
            "待删除模板",
            {
                "task_type": "google_sheet_C5",
                "token_type": "file",
                "token_file": "data/token.json",
                "spreadsheet_id": "sheet-delete",
                "sheet_name": "SheetDelete",
                "parameters": [["SPY"], [1], [2]],
            },
        )

    response = client.delete(f"/api/templates/{template_id}")

    assert response.status_code == 200
    data = response.get_json()
    assert data == {"status": "success", "message": "模板已删除"}

    with app.app_context():
        assert db.session.get(TaskTemplate, template_id) is None
