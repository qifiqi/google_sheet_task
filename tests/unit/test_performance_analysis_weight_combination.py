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


def test_schema_num_products_defaults_and_bounds():
    assert WeightCombinationSchema(task_id="task-1").num_products is None

    with pytest.raises(PydValidationError):
        WeightCombinationSchema(task_id="task-1", num_products=-1)

    with pytest.raises(PydValidationError):
        WeightCombinationSchema(task_id="task-1", num_products=101)


def test_num_products_pairs_fixed_anchor(monkeypatch):
    """必选 S1=70%，其余 5 只权重钉死 15%（下限=上限），组合产品数=2。

    钉死权重的可选产品在"不持仓 / 恰好 15%"之间二选一，产出 C(5,2)=10 个
    两两组合；总权重区间无需钉在 100% 来隐式固定权重。
    """
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 7)])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 5,
        "max_weight": 100,
        "min_weight": 50,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 70, "max_weight": 70},
            *[{"result_id": index, "min_weight": 15, "max_weight": 15} for index in range(2, 7)],
        ],
        "fixed_result_ids": [1],
        "num_products": 2,
    })

    assert len(combinations) == 10
    seen_pairs = set()
    for item in combinations:
        active = [stock for stock in item["stocks"] if stock["ratio"]]
        assert len(active) == 3
        assert active[0]["result_id"] == 1
        assert active[0]["ratio"] == 70
        assert all(stock["ratio"] == 15 for stock in active[1:])
        seen_pairs.add(frozenset(stock["result_id"] for stock in active[1:]))
    assert len(seen_pairs) == 10


def test_pinned_optional_products_toggle_between_zero_and_ratio(monkeypatch):
    """无必选时，钉死权重（下限=上限）的产品在 不持仓/该权重 之间二选一。"""
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 50,
        "max_weight": 100,
        "min_weight": 50,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 50, "max_weight": 50},
            {"result_id": 2, "min_weight": 50, "max_weight": 50},
        ],
    })

    ratio_pairs = {tuple(stock["ratio"] for stock in item["stocks"]) for item in combinations}
    assert ratio_pairs == {(50, 50), (50, 0), (0, 50)}


def test_num_products_without_fixed_counts_all_active(monkeypatch):
    """无必选产品时组合产品数 = 组合内持仓产品总数。"""
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 6)])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 50,
        "max_weight": 100,
        "min_weight": 50,
        "stock_ranges": [{"result_id": index, "max_weight": 50} for index in range(1, 6)],
        "num_products": 2,
    })

    # 每只只能取 0/50%，恰好 2 只非零 ⇒ C(5,2)=10
    assert len(combinations) == 10
    for item in combinations:
        assert len([stock for stock in item["stocks"] if stock["ratio"]]) == 2


def test_num_products_zero_keeps_only_fixed(monkeypatch):
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 4)])

    combinations = _combinations({
        "task_id": "task-1",
        "step": 10,
        "max_weight": 100,
        "min_weight": 50,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 70, "max_weight": 70},
            {"result_id": 2, "min_weight": 0, "max_weight": 30},
            {"result_id": 3, "min_weight": 0, "max_weight": 30},
        ],
        "fixed_result_ids": [1],
        "num_products": 0,
    })

    # 只要必选产品自身的唯一组合：S2/S3 都不持仓（70% ≥ 组合下限 50%）
    assert len(combinations) == 1
    assert [stock["ratio"] for stock in combinations[0]["stocks"]] == [70, 0, 0]


def test_num_products_rejects_impossible_counts(monkeypatch):
    _stub(monkeypatch, [_result(index, f"S{index}", f"Name{index}") for index in range(1, 4)])
    base = {
        "task_id": "task-1",
        "step": 10,
        "max_weight": 100,
        "min_weight": 0,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 70, "max_weight": 70},   # 必选产品
            {"result_id": 2, "min_weight": 0, "max_weight": 0},      # 上限 0，无法持仓
            {"result_id": 3, "min_weight": 0, "max_weight": 30},
        ],
        "fixed_result_ids": [1],
    }

    # 可变产品共 2 个，3 个超出
    with pytest.raises(ValidationError, match="超过可变产品数"):
        _combinations({**base, "num_products": 3})

    # 可变产品中能持仓的只有 1 个（S2 上限为 0），2 个超出
    with pytest.raises(ValidationError, match="可持仓的可变产品数"):
        _combinations({**base, "num_products": 2})


def test_fixed_result_ids_validation(monkeypatch):
    _stub(monkeypatch, [_result(1, "AAA", "Alpha"), _result(2, "BBB", "Beta")])
    base = {
        "task_id": "task-1",
        "step": 10,
        "max_weight": 100,
        "min_weight": 50,
        "stock_ranges": [
            {"result_id": 1, "min_weight": 0, "max_weight": 30},
            {"result_id": 2, "min_weight": 0, "max_weight": 30},
        ],
    }

    # 必选产品必须参与了组合
    with pytest.raises(ValidationError, match="必选产品不存在或未参与组合"):
        _combinations({**base, "fixed_result_ids": [99]})

    # 必选产品的单股上限不能为 0（无法持仓）
    with pytest.raises(ValidationError, match="单股上限不能为 0"):
        _combinations({
            **base,
            "fixed_result_ids": [2],
            "stock_ranges": [
                {"result_id": 1, "min_weight": 0, "max_weight": 30},
                {"result_id": 2, "min_weight": 0, "max_weight": 0},
            ],
        })

    with pytest.raises(PydValidationError):
        WeightCombinationSchema(task_id="task-1", fixed_result_ids=[1, "1"])
