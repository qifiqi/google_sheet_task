"""随机价格K线快照 API：任务维度列表/详情、结果反查与 CSV。"""

import json
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Task, TaskResultKlineLink, User
from app.repositories import task_kline_snapshot_repository, task_result_repository
from app.services.task_kline_snapshot_service import task_kline_snapshot_service
from app.utils.auth import create_access_token


def _rows(count=31):
    first = date(2026, 1, 1)
    return [
        {
            "stock_date": (first + timedelta(days=offset)).isoformat(),
            "open": 10.0,
            "high": 14.0,
            "low": 8.0,
            "close": 12.0,
            "data_source": "dfcf",
        }
        for offset in range(count)
    ]


@pytest.fixture()
def api_user(app_factory):
    with app_factory.app_context():
        user = User(username="kline-snapshot-api", password_hash="x")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(user.id, token_version=user.token_version)
        yield {"headers": {"Authorization": f"Bearer {token}"}}


def _seed_snapshot(app, *, with_link=True):
    with app.app_context():
        task = Task(
            id="task-kline-api",
            name="task-kline-api",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()
        source = task_kline_snapshot_service.get_or_create_source(
            task_id=task.id,
            stock_code="600000",
            stock_name="测试股票",
            market_type="cn",
            kline_key="2026-2025",
            data_source="dfcf",
            adjust_type="forward",
            rows=_rows(),
        )
        series = task_kline_snapshot_service.get_or_create_series(
            source=source,
            task_id=task.id,
            stock_code="600000",
            kline_key="2026-2025",
            random_group=1,
            price_mode="random_price",
            random_price_range="high_low",
            seed=f"{task.id}:600000:2026-2025:high_low:1",
            rows=_rows(),
        )
        result = task_result_repository.create_with_return(
            {
                "task_id": task.id,
                "step_index": 0,
                "parameters": json.dumps({
                    "stock_code": "600000",
                    "kline_series_id": series["id"] if with_link else None,
                }),
                "result": "{}",
                "success": True,
            },
            kline_series_id=series["id"] if with_link else None,
        )
        return task.id, series["id"], result["id"]


def _add_series(app, task_id, *, group=2):
    with app.app_context():
        source = task_kline_snapshot_repository.get_source(
            task_id, "600000", "2026-2025"
        )
        return task_kline_snapshot_service.get_or_create_series(
            source=source,
            task_id=task_id,
            stock_code="600000",
            kline_key="2026-2025",
            random_group=group,
            price_mode="random_price",
            random_price_range="high_low",
            seed=f"{task_id}:600000:2026-2025:high_low:{group}",
            rows=_rows(),
        )


def test_task_snapshot_list_requires_login(app_factory):
    app_factory.config.update(TESTING=True)
    task_id, _series_id, _result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(f"/api/tasks/{task_id}/kline-snapshots")

    assert response.status_code == 401
    assert response.get_json()["status"] == "error"


def test_task_snapshot_list_and_detail(app_factory, api_user):
    task_id, series_id, _result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 1
    assert data["current_page"] == 1
    items = data["items"]
    assert len(items) == 1
    assert items[0]["stock_name"] == "测试股票"
    assert items[0]["row_count"] == 31
    assert "values_json" not in items[0]

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots/{series_id}",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    detail = response.get_json()["data"]
    assert len(detail["rows"]) == 31
    assert detail["rows"][0]["stock_date"] == "2026-01-01"
    assert detail["series"]["seed"].endswith(":high_low:1")


def test_task_snapshot_detail_rejects_other_task(app_factory, api_user):
    _task_id, series_id, _result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/other-task/kline-snapshots/{series_id}",
        headers=api_user["headers"],
    )

    assert response.status_code == 404


def test_result_snapshot_endpoint_returns_rows(app_factory, api_user):
    _task_id, series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/results/{result_id}/kline-snapshot",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    detail = response.get_json()["data"]
    assert len(detail["rows"]) == 31
    assert detail["series"]["id"] == series_id
    assert detail["source"]["stock_name"] == "测试股票"


def test_result_snapshot_endpoint_returns_404_without_link(app_factory, api_user):
    _task_id, _series_id, result_id = _seed_snapshot(app_factory, with_link=False)
    client = app_factory.test_client()

    response = client.get(
        f"/api/results/{result_id}/kline-snapshot",
        headers=api_user["headers"],
    )

    assert response.status_code == 404
    assert "随机K线快照" in response.get_json()["message"]


def test_result_snapshot_csv(app_factory, api_user):
    _task_id, _series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/results/{result_id}/kline-snapshot?format=csv",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert "attachment" in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    assert text.splitlines()[0] == "stock_date,stock_val,open,high,low,close,vwap"
    assert "2026-01-01" in text.splitlines()[1]


def test_task_snapshot_csv(app_factory, api_user):
    task_id, series_id, _result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots/{series_id}?format=csv",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert response.get_data(as_text=True).splitlines()[0] == (
        "stock_date,stock_val,open,high,low,close,vwap"
    )


def test_result_detail_includes_kline_series_id(app_factory, api_user):
    _task_id, series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/results/{result_id}",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["kline_series_id"] == series_id


def test_task_snapshot_results_reverse_lookup(app_factory, api_user):
    task_id, series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots/{series_id}/results",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 1
    items = data["items"]
    assert [item["id"] for item in items] == [result_id]
    assert items[0]["step_index"] == 0
    assert items[0]["success"] is True


def test_task_snapshot_results_rejects_other_task(app_factory, api_user):
    _task_id, series_id, _result_id = _seed_snapshot(app_factory)
    with app_factory.app_context():
        db.session.add(Task(
            id="other-task",
            name="other-task",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        ))
        db.session.commit()
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/other-task/kline-snapshots/{series_id}/results",
        headers=api_user["headers"],
    )

    assert response.status_code == 404
    assert "随机K线快照" in response.get_json()["message"]


def test_delete_result_removes_kline_link(app_factory, api_user):
    _task_id, _series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.delete(
        f"/api/results/{result_id}",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    with app_factory.app_context():
        assert TaskResultKlineLink.query.filter_by(result_id=result_id).count() == 0


def test_task_snapshot_list_paginates(app_factory, api_user):
    task_id, _series_id, _result_id = _seed_snapshot(app_factory)
    _add_series(app_factory, task_id, group=2)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots?page=2&per_page=1",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 2
    assert data["current_page"] == 2
    assert data["per_page"] == 1
    assert [item["random_group"] for item in data["items"]] == [2]


def test_task_snapshot_bulk_csv(app_factory, api_user):
    task_id, _series_id, _result_id = _seed_snapshot(app_factory)
    _add_series(app_factory, task_id, group=2)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/kline-snapshots/export",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert (
        "task-task-kline-api-kline-snapshots.csv"
        in response.headers["Content-Disposition"]
    )
    text = response.get_data(as_text=True)
    assert text.startswith("\ufeff")
    lines = text.lstrip("\ufeff").splitlines()
    assert lines[0] == (
        "stock_code,stock_name,market_type,kline_key,dataset_key,"
        "random_group,random_price_range,stock_date,stock_val,"
        "open,high,low,close,vwap"
    )
    assert len(lines) == 1 + 2 * 31
    assert {line.split(",")[5] for line in lines[1:]} == {"1", "2"}


def test_task_snapshot_bulk_csv_without_snapshots(app_factory, api_user):
    with app_factory.app_context():
        db.session.add(Task(
            id="task-no-snap",
            name="task-no-snap",
            task_type="google_sheet_C7",
            status="completed",
            config="{}",
        ))
        db.session.commit()
    client = app_factory.test_client()

    response = client.get(
        "/api/tasks/task-no-snap/kline-snapshots/export",
        headers=api_user["headers"],
    )

    assert response.status_code == 404
    assert "随机K线快照" in response.get_json()["message"]


def test_task_results_include_kline_series_id(app_factory, api_user):
    task_id, series_id, result_id = _seed_snapshot(app_factory)
    client = app_factory.test_client()

    response = client.get(
        f"/api/tasks/{task_id}/results?page=1&per_page=20",
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert [item["id"] for item in items] == [result_id]
    assert items[0]["kline_series_id"] == series_id
