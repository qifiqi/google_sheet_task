import json

from app.extensions import db
from app.models import ScheduledTask


def _task(name, task_type, is_active):
    return ScheduledTask(
        name=name,
        description=f"{name} description",
        cron_expression="0 0 * * *",
        task_type=task_type,
        task_function="cleanup_old_data",
        task_params=json.dumps({"days": 10}),
        is_active=is_active,
    )


def test_scheduler_task_list_filters_by_keyword_type_and_active(app_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    app = app_factory
    with app.app_context():
        db.session.add_all([
            _task("daily cleanup", "cleanup", True),
            _task("weekly backup", "backup", True),
            _task("paused cleanup", "cleanup", False),
        ])
        db.session.commit()

    response = app.test_client().get(
        "/api/admin/scheduler/tasks",
        query_string={"keyword": "cleanup", "task_type": "cleanup", "is_active": "true"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["pagination"]["total"] == 1
    assert [item["name"] for item in payload["tasks"]] == ["daily cleanup"]
