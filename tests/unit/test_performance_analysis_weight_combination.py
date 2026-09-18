"""权重组合分析：产品装载、产品筛选、逐产品单股范围与组合枚举。"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydValidationError

from app.exceptions import ValidationError
from app.schemas.performance_analysis import WeightCombinationSchema
from app.services.performance_analysis import service

ROWS = [
    {"date": "2026-01-01", "index_return": 0.01, "start_return": 0.02},
    {"date": "2026-01-02", "index_return": 0.02, "start_return": 0.03},
]

METRICS = {
    "index_annualized_rates": [{"year": "all", "annualized_return": 0.1}],
    "start_annualized_rates": [{"year": "all", "annualized_return": 0.2}],
    "index_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": -0.1}},
    "start_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": -0.2}},
}


def _result(result_id, code, name, rows=None, product_index=None, ratio=None):
    parameters = {"stock_code": code, "stock_name": name}
    if product_index is not None:
        parameters["product_index"] = product_index
    if ratio is not None:
        parameters["ratio"] = ratio
    return SimpleNamespace(
        id=result_id,
        return_series_id=None,
        result={"return_date": ROWS if rows is None else rows},
        parameters=parameters,
    )


def _stub(monkeypatch, results, task=None):
    monkeypatch.setattr(service.task_repository, "get_required", lambda task_id: task or {"id": task_id})
    monkeypatch.setattr(
        service.task_result_repository, "list_preview_entities", lambda *args, **kwargs: results
    )
    monkeypatch.setattr(
        service.performance_analyzer, "_weight_combination_v1", lambda returns: METRICS
    )


def _combinations(payload):
    return list(service.performance_analysis_service.weight_combination(payload))


def test_weight_combination_yields_requested_metrics(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 25,
        "max_weight": 100,
        "min_weight": 50,
        "single_cap": 50,
    })

    # 每只 0~50%、总和 50~100%：(0,50) (25,25) (50,0) (25,50) (50,25) (50,50)
    assert len(combinations) == 6
    first = combinations[0]
    assert first["annualized_rates"] == {"index": 0.1, "start": 0.2}
    assert first["year_max_drawdown"] == {"index": -0.1, "start": -0.2}
    assert first["stocks"] == [
        {"result_id": 1, "stock_code": "AAA", "stock_name": "Alpha", "ratio": 0},
        {"result_id": 2, "stock_code": "BBB", "stock_name": "Beta", "ratio": 50},
    ]


def test_weight_combination_respects_per_stock_ranges(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 10,
        "max_weight": 100,
        "min_weight": 0,
        "single_cap": 100,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 20, "max_weight": 40},
            {"result_id": 2, "min_weight": 0, "max_weight": 30},
        ],
    })

    ratio_pairs = {tuple(stock["ratio"] for stock in item["stocks"]) for item in combinations}
    # AAA 3 档（20/30/40）× BBB 4 档（0/10/20/30）
    assert len(ratio_pairs) == 12
    # 下限把 AAA 固定进组合，上限封顶
    assert min(pair[0] for pair in ratio_pairs) == 20
    assert max(pair[0] for pair in ratio_pairs) == 40
    assert max(pair[1] for pair in ratio_pairs) == 30


def test_weight_combination_limits_to_selected_products(monkeypatch):
    _stub(monkeypatch, [
        _result(1, "AAA", "Alpha"),
        _result(2, "BBB", "Beta"),
        _result(3, "CCC", "Gamma"),
    ])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 50,
        "max_weight": 100,
        "min_weight": 50,
        "single_cap": 100,
        "result_ids": [1, 3],
    })

    assert combinations
    for item in combinations:
        assert [stock["result_id"] for stock in item["stocks"]] == [1, 3]


def test_weight_combination_rejects_unknown_selected_product(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha")])

    with pytest.raises(ValidationError, match="不存在或没有可用收益序列"):
        _combinations({"task_id": "task-1", "result_ids": [1, 99]})


def test_weight_combination_rejects_empty_selection(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha")])

    with pytest.raises(ValidationError, match="请至少选择一个参与组合的产品"):
        _combinations({"task_id": "task-1", "result_ids": []})


def test_stock_ranges_must_cover_products_exactly(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])
    base = {"task_id": "task-1", "step": 10, "stock_ranges": [{"result_id": 1, "max_weight": 30}]}

    with pytest.raises(ValidationError, match="缺少单股范围配置"):
        _combinations(dict(base))

    with pytest.raises(ValidationError, match="未参与组合的产品"):
        _combinations({
            **base,
            "result_ids": [1],
            "stock_ranges": [
                {"result_id": 1, "max_weight": 30},
                {"result_id": 2, "max_weight": 30},
            ],
        })

    with pytest.raises(ValidationError, match="重复"):
        _combinations({
            **base,
            "stock_ranges": [
                {"result_id": 1, "max_weight": 30},
                {"result_id": 1, "max_weight": 30},
                {"result_id": 2, "max_weight": 30},
            ],
        })


def test_weight_combination_rejects_infeasible_ranges(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])

    # 单股上限之和 40% 达不到组合总权重下限 50%
    with pytest.raises(ValidationError, match="无法达到组合总权重下限"):
        _combinations({
            "task_id": "task-1",
            "step": 10,
            "max_weight": 100,
            "min_weight": 50,
            "stock_ranges": [
                {"result_id": 1, "max_weight": 20},
                {"result_id": 2, "max_weight": 20},
            ],
        })

    # 单股下限之和 60% 超过组合总权重上限 50%
    with pytest.raises(ValidationError, match="超过组合总权重上限"):
        _combinations({
            "task_id": "task-1",
            "step": 10,
            "max_weight": 50,
            "min_weight": 0,
            "stock_ranges": [
                {"result_id": 1, "min_weight": 30, "max_weight": 50},
                {"result_id": 2, "min_weight": 30, "max_weight": 50},
            ],
        })


def test_ranges_allow_more_than_five_products(monkeypatch):
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 7)])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 50,
        "max_weight": 100,
        "min_weight": 50,
        "single_cap": 100,
        "stock_ranges": [{"result_id": index, "max_weight": 50} for index in range(1, 7)],
    })

    # 每只只能取 0/50%，总和 50~100% ⇒ 恰好 1 只或 2 只非零
    assert len(combinations) == 6 + 15


def test_legacy_path_still_caps_products_at_five(monkeypatch):
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 7)])

    with pytest.raises(ValidationError, match="暂时不支持超过 5 个产品"):
        _combinations({
            "task_id": "task-1",
            "step": 50,
            "max_weight": 100,
            "min_weight": 50,
            "single_cap": 50,
        })


def test_list_products_returns_configured_ratios(monkeypatch):
    task = SimpleNamespace(
        task_type="backtest_multi_product",
        config={"products": [{"ratio": "30"}, {"ratio": "70.0000"}]},
    )
    _stub(monkeypatch, [
        _result(1, "AAA", "Alpha", product_index=0),
        _result(2, "BBB", "Beta", product_index=1),
        _result(3, "CCC", "Gamma", rows=[], product_index=2),
    ], task=task)

    data = service.performance_analysis_service.list_weight_combination_products("task-1")

    assert data["task_type"] == "backtest_multi_product"
    # 序号 2 超出任务配置的产品数 ⇒ 比例缺省，前端回退到单股上限
    assert [product["ratio"] for product in data["products"]] == ["30", "70", None]
    # 没有收益序列的产品仍列出，但标记为不可用
    assert [product["has_returns"] for product in data["products"]] == [True, True, False]
    assert [product["stock_code"] for product in data["products"]] == ["AAA", "BBB", "CCC"]


def test_list_products_falls_back_to_result_ratio(monkeypatch):
    task = SimpleNamespace(task_type="backtest_training", config={})
    _stub(monkeypatch, [_result(1, "AAA", "Alpha", ratio="25.5")], task=task)

    data = service.performance_analysis_service.list_weight_combination_products("task-1")

    assert data["products"][0]["ratio"] == "25.5"


def test_schema_rejects_ranges_off_step_grid():
    with pytest.raises(PydValidationError):
        WeightCombinationSchema(
            task_id="task-1",
            step=10,
            stock_ranges=[{"result_id": 1, "min_weight": 0, "max_weight": 25}],
        )

    with pytest.raises(PydValidationError):
        WeightCombinationSchema(
            task_id="task-1",
            step=10,
            stock_ranges=[{"result_id": 1, "min_weight": 30, "max_weight": 20}],
        )

    with pytest.raises(PydValidationError):
        WeightCombinationSchema(
            task_id="task-1",
            step=10,
            stock_ranges=[
                {"result_id": 1, "min_weight": 0, "max_weight": 30},
                {"result_id": 1, "min_weight": 0, "max_weight": 30},
            ],
        )

    accepted = WeightCombinationSchema(
        task_id="task-1",
        step=10,
        single_cap=40,
        result_ids=[1, 2],
        stock_ranges=[
            {"result_id": 1, "min_weight": 0, "max_weight": 30},
            {"result_id": 2, "min_weight": 10, "max_weight": 40},
        ],
    )
    assert accepted.result_ids == [1, 2]
