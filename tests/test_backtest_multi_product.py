import json
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Task, TaskResult
from app.routes.backtest_multi_product import _build_global_preview_workbook
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    build_multi_product_global_preview_payload,
    normalize_multi_product_config,
)


def _base_product(index, ratio="50"):
    return {
        "product_index": index,
        "product_name": f"产品{index + 1}",
        "stock_code": f"TEST{index + 1}",
        "market_type": "cn",
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


def test_normalize_multi_product_config_validates_ratio_total():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, "60"), _base_product(1, "30")],
    }

    with pytest.raises(ValueError, match="比例合计必须为 100"):
        normalize_multi_product_config(config)


def test_normalize_multi_product_config_validates_parameter_alignment():
    product_1 = _base_product(0, "50")
    product_2 = _base_product(1, "50")
    product_2["parameters"] = product_2["parameters"][:1]
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [product_1, product_2],
    }

    with pytest.raises(ValueError, match="参数行数必须一致"):
        normalize_multi_product_config(config)


def _task_result_payload(index_return, start_return):
    return {
        "sheet__title": {
            "calculate_metrics": {
                "excess_returns": [{
                    "year": "all",
                    "index_annualized_return": index_return,
                    "start_annualized_return": start_return,
                    "annualized_return_diff": start_return - index_return,
                }],
                "index_profit_annual": 1,
                "start_profit_annual": 1,
                "index_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                "start_profit_monthly": [{"year": "all", "profit_monthly_percentage": 1}],
                "index_sharpe_ratios": {"all": {"avg_monthly_return": index_return, "sharpe_ratio": 2}},
                "start_sharpe_ratios": {"all": {"avg_monthly_return": start_return, "sharpe_ratio": 3}},
            }
        }
    }


def test_build_multi_product_global_preview_payload_weights_values(app_factory):
    app = app_factory
    with app.app_context():
        config = normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [_base_product(0, "25"), _base_product(1, "75")],
        })
        task = Task(
            id="multi-task",
            name="多品测试",
            task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
            status="completed",
            config=json.dumps(config, ensure_ascii=False),
            created_at=datetime.now(),
        )
        db.session.add(task)
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps({
                "product_index": 0,
                "product_name": "产品1",
                "stock_code": "TEST1",
                "ratio": "25",
                "parameter_group_index": 0,
                "parameter": config["products"][0]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload(0.10, 0.20)),
            success=True,
        ))
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=1,
            parameters=json.dumps({
                "product_index": 1,
                "product_name": "产品2",
                "stock_code": "TEST2",
                "ratio": "75",
                "parameter_group_index": 0,
                "parameter": config["products"][1]["parameters"][0],
            }, ensure_ascii=False),
            result=json.dumps(_task_result_payload(0.20, 0.40)),
            success=True,
        ))
        db.session.commit()

        payload = build_multi_product_global_preview_payload(task.id)

        assert payload["summary"]["product_count"] == 2
        row = payload["groups"][0]["rows"][0]
        assert row["metric"] == "年化收益"
        assert row["product_values"][0]["weighted_result_value"] == "5.00%"
        assert row["product_values"][1]["weighted_result_value"] == "30.00%"
        assert row["weighted_index_value"] == "17.50%"
        assert row["weighted_result_value"] == "35.00%"

        workbook = _build_global_preview_workbook(payload)
        sheet = workbook.active
        assert sheet["A1"].value == ""
        assert sheet["B1"].value == ""
        assert sheet["C1"].value == "产品1"
        assert sheet["F1"].value == "产品2"
        assert sheet["E2"].value == "模型结果（25%）"
        assert sheet["H2"].value == "模型结果（75%）"
        assert sheet["E3"].value == "5.00%"
        assert sheet["H3"].value == "30.00%"
        assert sheet["I2"].value == "比例计算-指数"
        assert sheet["J2"].value == "比例计算-结果"
        assert sheet["C1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["F1"].fill.fgColor.rgb == "00FCECC5"
        assert sheet["A2"].fill.fgColor.rgb == "00F7E1A1"
        assert sheet["A3"].fill.fgColor.rgb == "00F7E1A1"
