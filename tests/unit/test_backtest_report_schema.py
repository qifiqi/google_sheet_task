"""StrategyBacktestReportSchema 基准指数字段校验测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.backtest import StrategyBacktestReportSchema

_RETURNS = [
    {"date": "2024-01-01", "index_return": 0.01, "start_return": 0.02},
    {"date": "2024-01-02", "index_return": 0.02, "start_return": 0.01},
]


def _product(stock_code):
    return {
        "stock_code": stock_code,
        "product_name": stock_code,
        "returns": list(_RETURNS),
    }


def _rptm(products, **overrides):
    payload = {"report_type": "RPT-M", "products": products}
    payload.update(overrides)
    return payload


def test_index_benchmarks_defaults_to_empty_list():
    schema = StrategyBacktestReportSchema(**_rptm([_product("AAA.US"), _product("BBB.US")]))

    assert schema.index_benchmarks == []


def test_index_benchmarks_normalizes_ratio_shapes_and_dedupes():
    """比例兼容 50、"50%"、0.5（等价 50%）；仅代码+比例完全相同去重。"""
    schema = StrategyBacktestReportSchema(**_rptm(
        [_product("AAA.US"), _product("BBB.US"), _product("CCC.US")],
        index_benchmarks=[
            {"stock_code": " BBB.US ", "ratio": "50%"},
            {"stock_code": "BBB.US", "ratio": 50},
            {"stock_code": "AAA.US", "ratio": 0.5},
            {"stock_code": "CCC.US", "ratio": 30},
        ],
    ))

    assert [(item.stock_code, item.ratio) for item in schema.index_benchmarks] == [
        ("BBB.US", 50.0),
        ("AAA.US", 50.0),
        ("CCC.US", 30.0),
    ]


def test_index_benchmarks_defaults_ratio_to_100():
    schema = StrategyBacktestReportSchema(**_rptm(
        [_product("AAA.US"), _product("BBB.US")],
        index_benchmarks=[{"stock_code": "AAA.US"}],
    ))

    assert schema.index_benchmarks[0].ratio == 100.0


def test_index_benchmarks_rejects_more_than_three():
    products = [_product(code) for code in ("A1.US", "A2.US", "A3.US", "A4.US")]

    with pytest.raises(ValidationError, match="最多支持选择 3 条"):
        StrategyBacktestReportSchema(**_rptm(products, index_benchmarks=[
            {"stock_code": code, "ratio": 100} for code in ("A1.US", "A2.US", "A3.US", "A4.US")
        ]))


def test_index_benchmarks_rejects_non_list_value():
    with pytest.raises(ValidationError, match="必须是数组"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("BBB.US")],
            index_benchmarks="AAA.US",
        ))


def test_index_benchmarks_rejects_ratio_out_of_range():
    with pytest.raises(ValidationError, match="区间内"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("BBB.US")],
            index_benchmarks=[{"stock_code": "AAA.US", "ratio": 150}],
        ))


def test_index_code_must_exist_in_products():
    with pytest.raises(ValidationError, match="不在产品列表中"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("BBB.US")],
            index_benchmarks=[{"stock_code": "CCC.US", "ratio": 100}],
        ))


def test_index_code_must_hit_single_product():
    with pytest.raises(ValidationError, match="命中多个产品"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("AAA.US")],
            index_benchmarks=[{"stock_code": "AAA.US", "ratio": 100}],
        ))


def test_same_product_allowed_at_different_ratios():
    """语义 A：同一产品不同比例是两条合法基准。"""
    schema = StrategyBacktestReportSchema(**_rptm(
        [_product("AAA.US"), _product("BBB.US")],
        index_benchmarks=[
            {"stock_code": "AAA.US", "ratio": 50},
            {"stock_code": "AAA.US", "ratio": 100},
        ],
    ))

    assert [(item.stock_code, item.ratio) for item in schema.index_benchmarks] == [
        ("AAA.US", 50.0),
        ("AAA.US", 100.0),
    ]


def test_rpt_s_ignores_index_benchmarks_without_product_check():
    schema = StrategyBacktestReportSchema(
        report_type="RPT-S",
        returns=list(_RETURNS),
        index_benchmarks=[{"stock_code": "AAA.US", "ratio": 100}],
    )

    assert schema.index_benchmarks[0].stock_code == "AAA.US"


def test_rpt_s_validation_no_longer_references_undeclared_field():
    """回归：RPT-S 校验曾引用未声明字段 index_return_id 导致构造即崩。"""
    schema = StrategyBacktestReportSchema(report_type="RPT-S", returns=list(_RETURNS))

    assert schema.report_type == "RPT-S"
