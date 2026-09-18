"""回归守卫：多品全局预览的无风险利率（runtime_params）链路。

页面「计算预览」把页面上的无风险利率随请求交给后端后，必须满足：

1. 真正进入指标重算——rf≠0 时比例后单产品指标与组合指标都要按 rf 重算，
   不能复用执行时（rf=0）存下的快照，否则同一行里会混用两套口径；
2. 参与预览缓存隔离——同一任务同一比例下 rf 不同不能命中同一份缓存；
3. 载荷回显 runtime_params，页面据此回填输入框，保证"显示值 = 计算值"；
4. 非法输入走统一异常体系返回 400。

对应前端实现：static/js/pages/backtest_multi_product_global_preview.js
（calculateRatios 携带 runtime_params）。
"""
import json
from datetime import datetime

import pytest

from app.models import Task, TaskResult, db
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    _GLOBAL_PREVIEW_CACHE,
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


def _metrics_payload(index_return, start_return):
    return {
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


def _record_runtime_params(captured):
    """记录指标引擎收到的 runtime_params（无风险利率的最终落点）。"""

    def fake_metrics(return_date, runtime_params=None):
        captured.append(runtime_params)
        total_start = sum(item["start_return"] for item in return_date)
        total_index = sum(item["index_return"] for item in return_date)
        return _metrics_payload(total_index, total_start)

    return fake_metrics


def _seed_preview_task(app, task_id, saved_ratio="50"):
    """两个产品、各带收益序列的已完成任务；存档比例与预览比例一致。

    存档比例与预览比例一致很关键：rf=0 时后端会直接复用执行时快照，
    只有 rf≠0 才必须重算，正是本文件要锁定的分支。
    """
    config = normalize_multi_product_config({
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [_base_product(0, saved_ratio), _base_product(1, saved_ratio)],
    })
    task = Task(
        id=task_id,
        name="无风险利率预览回归",
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
                # 执行时落库的比例后指标快照（rf=0 口径）：比例未变且 rf=0 时后端直接复用它，
                # rf≠0 时必须按收益序列重算，否则同一行会混用两套口径。
                "calculate_metrics": _metrics_payload(ir, sr),
                "weighted_calculate_metrics": _metrics_payload(ir, sr),
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
                "ratio": saved_ratio,
                "parameter_group_index": 0,
                "parameter": config["products"][idx]["parameters"],
            }, ensure_ascii=False),
            result=json.dumps(payload),
            success=True,
        ))
    db.session.commit()
    return task


def test_preview_risk_free_rate_reaches_metrics_engine(app_factory, monkeypatch):
    """rf≠0：比例后单产品指标与组合指标都按 rf 重算，并在载荷里回显。"""
    app = app_factory
    _GLOBAL_PREVIEW_CACHE.clear()
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _record_runtime_params(captured),
    )

    with app.app_context():
        _seed_preview_task(app, "rf-preview-task")
        ratios_override = [{"ratio": 50}, {"ratio": 50}]

        default_payload = build_multi_product_global_preview_payload(
            "rf-preview-task", ratios_override=ratios_override
        )
        # 默认口径（rf=0）：比例未变 → 复用执行快照，只算组合指标一次。
        assert len(captured) == 1
        assert captured[0] is None
        assert default_payload["runtime_params"]["risk_free_rate"] == 0

        captured.clear()
        rf_payload = build_multi_product_global_preview_payload(
            "rf-preview-task",
            ratios_override=ratios_override,
            runtime_params={"risk_free_rate": 0.03},
        )

        # 两个产品的比例后指标 + 组合指标：全部按 rf=0.03 重算。
        assert len(captured) == 3
        assert all(round(params.risk_free_rate, 6) == 0.03 for params in captured)
        # 载荷回显本次口径，页面按它回填输入框。
        assert round(rf_payload["runtime_params"]["risk_free_rate"], 6) == 0.03
        assert rf_payload["groups"][0]["rows"]


def test_preview_cache_isolates_risk_free_rate(app_factory, monkeypatch):
    """缓存按 rf 隔离：rf 不同必须重算，rf 相同（含显式 0）仍命中缓存。"""
    app = app_factory
    _GLOBAL_PREVIEW_CACHE.clear()
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _record_runtime_params(captured),
    )

    with app.app_context():
        _seed_preview_task(app, "rf-cache-task")
        ratios_override = [{"ratio": 50}, {"ratio": 50}]

        build_multi_product_global_preview_payload(
            "rf-cache-task", ratios_override=ratios_override
        )
        calls_after_default = len(captured)

        # 显式 rf=0 与缺省同一口径：命中缓存，不重算。
        build_multi_product_global_preview_payload(
            "rf-cache-task",
            ratios_override=ratios_override,
            runtime_params={"risk_free_rate": 0},
        )
        assert len(captured) == calls_after_default

        rf_payload = build_multi_product_global_preview_payload(
            "rf-cache-task",
            ratios_override=ratios_override,
            runtime_params={"risk_free_rate": 0.03},
        )
        calls_after_rf = len(captured)
        assert calls_after_rf > calls_after_default

        # 再次相同 rf：命中 rf=0.03 的缓存，指标引擎不再被调用。
        cached_payload = build_multi_product_global_preview_payload(
            "rf-cache-task",
            ratios_override=ratios_override,
            runtime_params={"risk_free_rate": 0.03},
        )
        assert len(captured) == calls_after_rf
        assert cached_payload["runtime_params"] == rf_payload["runtime_params"]


def test_calculate_ratios_endpoint_forwards_risk_free_rate(app_factory, monkeypatch):
    """计算预览端点：请求里的 runtime_params 原样进入重算链路。"""
    app = app_factory
    _GLOBAL_PREVIEW_CACHE.clear()
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _record_runtime_params(captured),
    )

    with app.app_context():
        _seed_preview_task(app, "rf-http-task")

    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = app.test_client()
    response = client.post(
        "/backtest-multi-product/api/global-preview/rf-http-task/calculate-ratios",
        json={
            "ratios": [{"product_index": 0, "ratio": 50}, {"product_index": 1, "ratio": 50}],
            "runtime_params": {"risk_free_rate": 0.03},
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert round(body["data"]["runtime_params"]["risk_free_rate"], 6) == 0.03
    assert captured and all(round(params.risk_free_rate, 6) == 0.03 for params in captured)


def test_calculate_ratios_endpoint_rejects_invalid_risk_free_rate(app_factory):
    """非法无风险利率：400 + 绩效分析同一套报错文案，不落入 500。"""
    app = app_factory
    with app.app_context():
        _seed_preview_task(app, "rf-invalid-task")

    monkeypatch_auth = pytest.MonkeyPatch()
    monkeypatch_auth.setenv("AUTH_ENABLED", "false")
    try:
        client = app.test_client()
        response = client.post(
            "/backtest-multi-product/api/global-preview/rf-invalid-task/calculate-ratios",
            json={
                "ratios": [{"product_index": 0, "ratio": 50}, {"product_index": 1, "ratio": 50}],
                "runtime_params": {"risk_free_rate": "abc"},
            },
        )
    finally:
        monkeypatch_auth.undo()

    assert response.status_code == 400
    assert "无风险利率必须是数字" in response.get_json()["message"]


def test_preview_logs_compute_start_and_cache_hit(app_factory, monkeypatch, caplog):
    """后端留痕：开始计算与命中缓存各一条 INFO，且带上本次无风险利率。"""
    import logging

    app = app_factory
    _GLOBAL_PREVIEW_CACHE.clear()
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _record_runtime_params([]),
    )

    with app.app_context():
        _seed_preview_task(app, "rf-log-task")
        ratios_override = [{"ratio": 50}, {"ratio": 50}]
        with caplog.at_level(logging.INFO, logger="app.services.backtest_multi_product_preview"):
            build_multi_product_global_preview_payload(
                "rf-log-task",
                ratios_override=ratios_override,
                runtime_params={"risk_free_rate": 0.03},
            )
            build_multi_product_global_preview_payload(
                "rf-log-task",
                ratios_override=ratios_override,
                runtime_params={"risk_free_rate": 0.03},
            )

    messages = [record.getMessage() for record in caplog.records]
    compute_logs = [message for message in messages if "开始计算" in message]
    cache_logs = [message for message in messages if "命中缓存" in message]
    assert len(compute_logs) == 1
    assert "risk_free_rate=0.0300" in compute_logs[0]
    assert len(cache_logs) == 1
    assert "risk_free_rate=0.0300" in cache_logs[0]


def test_global_preview_query_forwards_risk_free_rate(app_factory, monkeypatch):
    """GET 预览（页面首次加载）：risk_free_rate 查询参数同样进入重算链路。"""
    app = app_factory
    _GLOBAL_PREVIEW_CACHE.clear()
    captured = []
    monkeypatch.setattr(
        "app.services.backtest_multi_product_service.performance_analyzer.get_calculate_metrics_v1",
        _record_runtime_params(captured),
    )

    with app.app_context():
        _seed_preview_task(app, "rf-get-task")

    monkeypatch.setenv("AUTH_ENABLED", "false")
    client = app.test_client()
    response = client.get(
        "/backtest-multi-product/api/global-preview/rf-get-task?risk_free_rate=0.03"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert round(body["data"]["runtime_params"]["risk_free_rate"], 6) == 0.03
    assert captured and all(round(params.risk_free_rate, 6) == 0.03 for params in captured)
