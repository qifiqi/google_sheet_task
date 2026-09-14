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


def test_index_stock_code_defaults_to_empty_list():
    schema = StrategyBacktestReportSchema(**_rptm([_product("AAA.US"), _product("BBB.US")]))

    assert schema.index_stock_code == []


def test_index_stock_code_strips_dedupes_and_preserves_order():
    schema = StrategyBacktestReportSchema(**_rptm(
        [_product("AAA.US"), _product("BBB.US"), _product("CCC.US")],
        index_stock_code=[" BBB.US ", "", "BBB.US", "AAA.US"],
    ))

    assert schema.index_stock_code == ["BBB.US", "AAA.US"]


def test_index_stock_code_rejects_more_than_three():
    codes = ["A1.US", "A2.US", "A3.US", "A4.US"]
    products = [_product(code) for code in codes]

    with pytest.raises(ValidationError, match="最多支持选择 3 个"):
        StrategyBacktestReportSchema(**_rptm(products, index_stock_code=codes))


def test_index_stock_code_rejects_string_input():
    with pytest.raises(ValidationError, match="股票代码数组"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("BBB.US")],
            index_stock_code="AAA.US",
        ))


def test_index_code_must_exist_in_products():
    with pytest.raises(ValidationError, match="不在产品列表中"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("BBB.US")],
            index_stock_code=["CCC.US"],
        ))


def test_index_code_must_hit_single_product():
    with pytest.raises(ValidationError, match="命中多个产品"):
        StrategyBacktestReportSchema(**_rptm(
            [_product("AAA.US"), _product("AAA.US")],
            index_stock_code=["AAA.US"],
        ))


def test_rpt_s_ignores_index_codes_without_product_check():
    schema = StrategyBacktestReportSchema(
        report_type="RPT-S",
        returns=list(_RETURNS),
        index_stock_code=["AAA.US"],
    )

    assert schema.index_stock_code == ["AAA.US"]


def test_rpt_s_validation_no_longer_references_undeclared_field():
    """回归：RPT-S 校验曾引用未声明字段 index_return_id 导致构造即崩。"""
    schema = StrategyBacktestReportSchema(report_type="RPT-S", returns=list(_RETURNS))

    assert schema.report_type == "RPT-S"
