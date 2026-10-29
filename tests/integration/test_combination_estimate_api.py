"""组合数精算 API：鉴权、custom 公式路径与参数校验。"""

import pytest

from app.extensions import db
from app.models import User
from app.utils.auth import create_access_token


@pytest.fixture()
def api_user(app_factory):
    with app_factory.app_context():
        user = User(username="estimate-api-user", password_hash="x")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(user.id, token_version=user.token_version)
        yield {"headers": {"Authorization": f"Bearer {token}"}}


def test_estimate_requires_login(app_factory):
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
