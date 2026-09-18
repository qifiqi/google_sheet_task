"""权重组合分析产品列表接口（GET /performance_analysis/v1/weight_combination/products）
与带产品筛选/单股范围的分析请求（POST /performance_analysis/v1/weight_combination）。

覆盖鉴权、query 校验、任务不存在、多品配置比例回填、"无收益序列"标记，
以及组合枚举是否遵守选中的产品与单股范围。
"""

import json
import secrets

from werkzeug.security import generate_password_hash

ROWS = [
    {"date": f"2026-01-{day:02d}", "index_return": 0.001 * (1 if day % 2 else -1), "start_return": 0.002 * (1 if day % 2 else -1)}
    for day in range(1, 21)
]


def _login(app):
    from app.extensions import db
    from app.models import User

    password = secrets.token_hex(12)
    with app.app_context():
        db.session.add(User(
            username="wc-analyst",
            password_hash=generate_password_hash(password),
            is_active=True,
        ))
        db.session.commit()

    client = app.test_client()
    resp = client.post("/api/auth/login", json={"username": "wc-analyst", "password": password})
    # 错误响应只有"Accept 优先 JSON"才走统一信封（app/errors.py 的 API 路径判定），
    # 补上 fetch 默认携带的 Accept: */*，与页面真实请求一致。
    return client, {
        "Authorization": "Bearer " + resp.get_json()["data"]["access_token"],
        "Accept": "*/*",
    }


def _seed_task(app, task_id):
    """造一个多品任务：2 只有收益序列的产品 + 1 只结果为空的产品，返回结果 ID 列表。"""
    from app.extensions import db
    from app.models import Task, TaskResult

    result_ids = []
    with app.app_context():
        db.session.add(Task(
            id=task_id,
            name="权重组合产品列表",
            task_type="backtest_multi_product",
            status="completed",
            config=json.dumps(
                {"products": [{"ratio": "40"}, {"ratio": "60"}]},
                ensure_ascii=False,
            ),
        ))
        for step_index, (code, name) in enumerate([("AAA", "Alpha"), ("BBB", "Beta"), ("CCC", "Gamma")]):
            result = TaskResult(
                task_id=task_id,
                step_index=step_index,
                success=True,
                parameters=json.dumps(
                    {"stock_code": code, "stock_name": name, "product_index": step_index},
                    ensure_ascii=False,
                ),
                result=json.dumps({"return_date": ROWS if step_index < 2 else []}, ensure_ascii=False),
            )
            db.session.add(result)
            db.session.flush()
            result_ids.append(result.id)
        db.session.commit()
    return result_ids


def test_products_endpoint_requires_auth(app_factory):
    client = app_factory.test_client()
    resp = client.get(
        "/performance_analysis/v1/weight_combination/products?task_id=any",
        headers={"Accept": "*/*"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["status"] == "error"


def test_products_endpoint_rejects_missing_task_id(app_factory):
    client, headers = _login(app_factory)
    resp = client.get("/performance_analysis/v1/weight_combination/products", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_products_endpoint_returns_ratios_and_availability(app_factory):
    client, headers = _login(app_factory)
    _seed_task(app_factory, "wc-task-1")

    resp = client.get(
        "/performance_analysis/v1/weight_combination/products?task_id=wc-task-1",
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["task_id"] == "wc-task-1"
    assert data["task_type"] == "backtest_multi_product"
    assert [
        (item["stock_code"], item["stock_name"], item["ratio"], item["has_returns"])
        for item in data["products"]
    ] == [
        ("AAA", "Alpha", "40", True),
        ("BBB", "Beta", "60", True),
        ("CCC", "Gamma", None, False),
    ]


def test_products_endpoint_returns_404_for_unknown_task(app_factory):
    client, headers = _login(app_factory)
    resp = client.get(
        "/performance_analysis/v1/weight_combination/products?task_id=missing-task",
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.get_json()["status"] == "error"


def test_analysis_stream_honours_selection_and_ranges(app_factory):
    client, headers = _login(app_factory)
    result_ids = _seed_task(app_factory, "wc-task-2")

    resp = client.post(
        "/performance_analysis/v1/weight_combination",
        json={
            "task_id": "wc-task-2",
            "step": 25,
            "max_weight": 100,
            "min_weight": 50,
            "single_cap": 30,
            # 只选前两只产品；CCC 无收益序列，本来也不参与
            "result_ids": [result_ids[0], result_ids[1]],
            "stock_ranges": [
                {"result_id": result_ids[0], "min_weight": 0, "max_weight": 25},
                {"result_id": result_ids[1], "min_weight": 25, "max_weight": 50},
            ],
        },
        headers=headers,
    )

    assert resp.status_code == 200
    combos = [json.loads(line) for line in resp.get_data(as_text=True).splitlines() if line.strip()]
    assert combos
    assert all("error" not in combo for combo in combos)

    for combo in combos:
        ratios = {stock["stock_code"]: stock["ratio"] for stock in combo["stocks"]}
        assert set(ratios) == {"AAA", "BBB"}
        assert ratios["AAA"] <= 25
        assert ratios["BBB"] >= 25
        assert ratios["BBB"] <= 50
        assert 50 <= sum(ratios.values()) <= 100

    # AAA 0~25、BBB 25~50、总和 50~100 ⇒ (0,50) (25,25) (25,50)
    assert sorted(sorted(combo["stocks"], key=lambda stock: stock["stock_code"])[0]["ratio"] for combo in combos) == [0, 25, 25]


def test_analysis_endpoint_rejects_ranges_off_grid(app_factory):
    client, headers = _login(app_factory)
    result_ids = _seed_task(app_factory, "wc-task-3")

    resp = client.post(
        "/performance_analysis/v1/weight_combination",
        json={
            "task_id": "wc-task-3",
            "step": 25,
            "single_cap": 30,
            "stock_ranges": [
                {"result_id": result_ids[0], "min_weight": 0, "max_weight": 20},
                {"result_id": result_ids[1], "min_weight": 0, "max_weight": 50},
            ],
        },
        headers={**headers, "Accept": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"
