"""回归守卫：多品全局预览在产品比例为 0 时保留完整占位。

背景（2026-09-07）：前端 global_preview 把统一信封当数据使用（缺
``data.data`` 解包），点击"计算预览/保存比例"后 products/groups 变
undefined，页面表现为"按钮无效 + 比例 0 的产品占位消失"。本文件锁定
两侧契约：后端在 ratio=0 时仍返回该产品的指数/模型结果占位，仅加权
贡献（模型结果(0%)）为 0；calculate-ratios 端点返回统一信封。
"""
import json
from datetime import datetime

from app.models import Task, TaskResult, db
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    normalize_multi_product_config,
)
from app.services.backtest_multi_product_preview import (
    build_multi_product_global_preview_payload,
)


def _base_product(index, ratio):
    return {
        "product_index": index,
        "product_name": f"产品{index + 1}",
        "stock_code": f"TEST{index + 1}",
        "market_type": "cn",
        "price_mode": "sp_price",
        "ratio": ratio,
        "sheet": {
            "spreadsheet_id": f"sheet-{index + 1}",
            "sheet_name": "data",
            "title": "C3 model",
        },
        "parameters": [
            ["0.0350%", "1", "2", "3", "4", "5", "6", "7"],
            ["0.0350%", "8", "9", "10", "11", "12", "13", "14"],
        ],
    }


def _fake_metrics_factory(captured):
    def fake_metrics(return_date):
        captured.append(return_date)
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return {
            "excess_returns": [{
                "year": "all",
                "index_annualized_return": total_index,
                "start_annualized_return": total_start,
                "annualized_return_diff": total_start - total_index,
            }],
            "index_profit_annual": 1,
            "start_profit_annual": 1,
            "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
            "index_sharpe_ratios": {"all": {"avg_monthly_return": total_index, "sharpe_ratio": 2}},
            "start_sharpe_ratios": {"all": {"avg_monthly_return": total_start, "sharpe_ratio": 3}},
        }

    return fake_metrics


def _seed_zero_ratio_task(app, task_id):
    config = normalize_multi_product_config({
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, "25"), _base_product(1, "75")],
    })
    task = Task(
        id=task_id,
        name="零比例回归",
        task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
        status="completed",
        config=json.dumps(config, ensure_ascii=False),
        created_at=datetime.now(),
    )
    db.session.add(task)
    for idx, (ir, sr) in enumerate([(0.10, 0.20), (0.20, 0.40)]):
        returns = [
            {"date": "2024-01-01", "index_return": 1 + idx * 9, "start_return": 2 + idx * 18},
            {"date": "2024-01-02", "index_return": 3 + idx * 27, "start_return": 4 + idx * 36},
        ]
        payload = {
            "sheet__title": {
                "calculate_metrics": {
                    "excess_returns": [{
                        "year": "all",
                        "index_annualized_return": ir,
                        "start_annualized_return": sr,
                        "annualized_return_diff": sr - ir,
                    }],
                    "index_profit_annual": 1,
                    "start_profit_annual": 1,
                    "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                    "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                    "index_sharpe_ratios": {"all": {"avg_monthly_return": ir, "sharpe_ratio": 2}},
                    "start_sharpe_ratios": {"all": {"avg_monthly_return": sr, "sharpe_ratio": 3}},
                },
                "return_date": returns,
            }
        }
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=idx,
            parameters=json.dumps({
                "product_index": idx,
                "product_name": f"产品{idx + 1}",
                "stock_code": f"TEST{idx + 1}",
                "ratio": "50",
                "parameter_group_index": 0,
                "parameter": config["products"][idx]["parameters"],
            }, ensure_ascii=False),
            result=json.dumps(payload),
            success=True,
        ))
    db.session.commit()
    return task


def test_zero_ratio_product_keeps_placeholder_and_zero_weighted(app_factory, monkeypatch):
    app = app_factory
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _fake_metrics_factory(captured),
    )

    with app.app_context():
        _seed_zero_ratio_task(app, "zero-ratio-payload")

        payload = build_multi_product_global_preview_payload(
            "zero-ratio-payload",
            ratios_override=[{"ratio": 100}, {"ratio": 0}],
        )
        assert payload is not None
        # 产品列表完整：比例为 0 的产品占位仍然存在。
        assert [p["ratio"] for p in payload["products"]] == ["100", "0"]

        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert len(row["product_values"]) == 2

        first, zero = row["product_values"]
        # 比例 0 的产品：指数 / 模型结果列仍返回真实值。
        assert zero["index_value"] == "20.00%"
        assert zero["result_value"] == "40.00%"
        # 加权贡献（模型结果(0%)）全为 0。
        assert zero["weighted_result_value"] == "0.00%"
        assert zero["raw_weighted_result_value"] == 0
        # 满比例产品的加权贡献与组合行照常返回。
        assert first["weighted_result_value"] == "600.00%"
        assert row["weighted_result_value"] == "600.00%"


def test_calculate_ratios_endpoint_returns_enveloped_payload(app_factory, monkeypatch):
    app = app_factory
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _fake_metrics_factory(captured),
    )

    with app.app_context():
        _seed_zero_ratio_task(app, "zero-ratio-http")

    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = app.test_client()
    response = client.post(
        "/backtest-multi-product/api/global-preview/zero-ratio-http/calculate-ratios",
        json={"ratios": [{"product_index": 0, "ratio": 100}, {"product_index": 1, "ratio": 0}]},
    )

    assert response.status_code == 200
    body = response.get_json()
    # 统一信封：前端必须从 data 取 products/groups。
    assert body["status"] == "success"
    assert [p["ratio"] for p in body["data"]["products"]] == ["100", "0"]
    assert body["data"]["groups"] and body["data"]["groups"][0]["rows"]
