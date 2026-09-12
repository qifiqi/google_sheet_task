"""收益序列导出接口回归：直查收益表、纯数据载荷、比例权重与校验。

覆盖 POST /backtest-multi-product/api/global-preview/<task_id>/return-series：
- 数据直查 t_param_task_results_return（list_return_entities_in_write_order），按
  stock_code 归位产品、写入序定位参数方案；
- 序列行原样返回累计收益（index_return / start_return），无任何派生列——
  净值/当天收益率/比例组合全部由前端 Excel 公式计算；
- 多产品任务附带比例与统一权重（portfolio_combiner.normalize_weight），
  ratios 覆盖时数量必须与产品数一致（否则 400）。
"""
import json
from datetime import datetime

import pytest

from app.models import Task, TaskResultReturn, db
from app.services.backtest_multi_product_preview import (
    build_return_series_export_payload,
)
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    normalize_multi_product_config,
)
from app.utils.return_series import build_return_series_fields

P0_ROWS = [
    {"date": "2024-01-01", "index_return": 0.10, "start_return": 0.20},
    {"date": "2024-01-02", "index_return": 0.21, "start_return": 0.42},
]
P1_ROWS = [
    {"date": "2024-01-01", "index_return": 0.30, "start_return": 0.05},
    {"date": "2024-01-02", "index_return": 0.72, "start_return": 0.10},
]
GROUP1_P0_ROWS = [
    {"date": "2024-01-01", "index_return": 0.05, "start_return": 0.06},
    {"date": "2024-01-02", "index_return": 0.08, "start_return": 0.09},
    {"date": "2024-01-03", "index_return": 0.11, "start_return": 0.12},
]


def _base_product(index, ratio):
    return {
        "product_index": index,
        "product_name": f"产品{index + 1}",
        "stock_code": f"600519" if index == 0 else "000001",
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
        ],
    }


def _seed_return_entity(task_id, stock_code, stock_name, rows):
    fields = build_return_series_fields(
        rows, stock_code=stock_code, stock_name=stock_name, market_type="cn",
    )
    db.session.add(TaskResultReturn(task_id=task_id, **fields))


def _seed_multi_product_task(app, task_id):
    config = normalize_multi_product_config({
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, "25"), _base_product(1, "75")],
    })
    task = Task(
        id=task_id,
        name="收益序列导出",
        task_type=BACKTEST_MULTI_PRODUCT_TASK_TYPE,
        status="completed",
        config=json.dumps(config, ensure_ascii=False),
        created_at=datetime.now(),
    )
    db.session.add(task)
    # 写入序 = 参数方案序：产品 0 先写方案 0，再写方案 1；产品 1 只写方案 0。
    _seed_return_entity(task.id, "600519", "产品1", P0_ROWS)
    _seed_return_entity(task.id, "000001", "产品2", P1_ROWS)
    _seed_return_entity(task.id, "600519", "产品1", GROUP1_P0_ROWS)
    db.session.commit()
    return task


def test_pure_data_payload_with_weights(app_factory):
    with app_factory.app_context():
        _seed_multi_product_task(app_factory, "rse-default")

        payload = build_return_series_export_payload("rse-default")

        assert payload is not None
        assert payload["task"]["is_multi_product"] is True
        assert payload["options"]["ratios_source"] == "default"
        # 产品比例与统一权重（normalize_weight：25 → 0.25，不归一化到 1）。
        assert [(p["ratio"], p["weight"], p["included"]) for p in payload["products"]] == [
            ("25", pytest.approx(0.25), True),
            ("75", pytest.approx(0.75), True),
        ]
        # 默认返回全部方案：600519 写入序 0/1 → 方案 0/1，000001 → 方案 0。
        assert [(e["group_key"], e["product_index"]) for e in payload["series"]] == [
            ("0", 0),
            ("0", 1),
            ("1", 0),
        ]
        entry = payload["series"][0]
        assert entry["stock_code"] == "600519.SS"
        assert entry["weight"] == pytest.approx(0.25)
        assert entry["included"] is True
        # 序列原样返回累计收益三列，无任何派生列（净值/日收益由前端公式计算）。
        assert set(entry["rows"][0]) == {"date", "index_return", "start_return"}
        assert entry["rows"][1]["index_return"] == pytest.approx(0.21)
        assert entry["return_length"] == 2


def test_ratios_override_rewrites_products_meta(app_factory):
    with app_factory.app_context():
        _seed_multi_product_task(app_factory, "rse-override")

        payload = build_return_series_export_payload(
            "rse-override",
            ratios_override=[
                {"product_index": 0, "ratio": 100},
                {"product_index": 1, "ratio": 0},
            ],
        )

        assert payload["options"]["ratios_source"] == "override"
        assert [(p["ratio"], p["weight"], p["included"]) for p in payload["products"]] == [
            ("100", pytest.approx(1.0), True),
            ("0", None, False),
        ]
        # 比例 0 产品的序列仍然返回（sheet 照常导出），由前端决定不进组合公式。
        assert payload["series"][1]["included"] is False
        assert payload["series"][1]["weight"] is None


def test_group_key_filters_series_by_write_order(app_factory):
    with app_factory.app_context():
        _seed_multi_product_task(app_factory, "rse-group")

        payload = build_return_series_export_payload("rse-group", group_key="1")

        # 方案 1 只有产品 0（TEST1 的第二次写入）。
        assert [entry["group_key"] for entry in payload["series"]] == ["1"]
        assert payload["series"][0]["return_length"] == 3


def test_return_series_endpoint_envelope_and_validation(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        _seed_multi_product_task(app, "rse-http")
        # 单品任务：纯数据接口同样可用（只返回序列，无比例元信息）。
        single = Task(
            id="rse-single",
            name="单品任务",
            task_type="backtest_training",
            status="completed",
            config=json.dumps({"stock_code": "TEST1"}),
            created_at=datetime.now(),
        )
        db.session.add(single)
        db.session.commit()

    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = app.test_client()

    ok = client.post(
        "/backtest-multi-product/api/global-preview/rse-http/return-series",
        json={},
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["status"] == "success"
    assert body["data"]["series"]
    assert body["data"]["products"][0]["weight"] == pytest.approx(0.25)

    mismatch = client.post(
        "/backtest-multi-product/api/global-preview/rse-http/return-series",
        json={"ratios": [{"product_index": 0, "ratio": 100}]},
    )
    assert mismatch.status_code == 400
    assert "比例数量" in mismatch.get_json()["message"]

    single_response = client.post(
        "/backtest-multi-product/api/global-preview/rse-single/return-series",
        json={},
    )
    assert single_response.status_code == 200
    single_body = single_response.get_json()
    assert single_body["data"]["task"]["is_multi_product"] is False
    assert single_body["data"]["products"] == []
