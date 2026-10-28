"""组合数精算 API：鉴权、custom 公式路径与参数校验。"""

import pytest

from app.extensions import db
from app.models import User


@pytest.fixture()
def api_user(app_factory, monkeypatch):
    # 单 Token 子服务模式：本地登录退役，免鉴权 mock 用户替代。
    monkeypatch.setenv("AUTH_ENABLED", "false")
    yield {"headers": {}}


def test_estimate_requires_login(app_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    client = app_factory.test_client()

    response = client.post(
        "/api/google-sheet/combination-estimate",
        json={"task_type": "google_sheet_c7", "config": {}},
    )

    assert response.status_code == 401


def test_estimate_custom_formula_endpoint(app_factory, api_user):
    client = app_factory.test_client()

    response = client.post(
        "/api/google-sheet/combination-estimate",
        json={
            "task_type": "google_sheet_c1_1",
            "config": {
                "kline_source": "custom",
                "price_mode": "random_price",
                "random_group_count": 4,
                "parameters": [["A", "B", "C"]],
            },
        },
        headers=api_user["headers"],
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "estimated_count": 12,
        "source": "formula",
    }


def test_estimate_rejects_unknown_task_type(app_factory, api_user):
    client = app_factory.test_client()

    response = client.post(
        "/api/google-sheet/combination-estimate",
        json={"task_type": "google_sheet_c3", "config": {"parameters": [["A"]]}},
        headers=api_user["headers"],
    )

    assert response.status_code == 400
    assert "C5/C7/C1.1" in response.get_json()["message"]
