from __future__ import annotations

import pytest

from app.services.performance_analysis.portfolio_combiner import (
    combine_product_returns,
    normalize_weight,
)


def test_normalize_weight_accepts_decimal_and_percent_forms():
    assert normalize_weight("30") == normalize_weight("30%") == normalize_weight("0.3")
    assert float(normalize_weight("30%")) == pytest.approx(0.30)


def test_daily_compound_is_the_single_weighting_algorithm():
    first = [
        {"date": "2026-01-01", "index_return": 0.10, "start_return": 0.10},
        {"date": "2026-01-02", "index_return": 0.21, "start_return": 0.21},
    ]
    second = [
        {"date": "2026-01-01", "index_return": 0.20, "start_return": 0.20},
        {"date": "2026-01-02", "index_return": 0.44, "start_return": 0.44},
    ]
    products = [{"returns": first, "ratio": "50"}, {"returns": second, "ratio": "50"}]
    daily = combine_product_returns(products)
    assert daily[-1]["start_return"] == pytest.approx(0.3225)
    # 旧版累计收益直接加权算法已停用；传入 legacy 标志也按日收益加权后复利。
    assert combine_product_returns(products, weighting_mode="legacy_cumulative") == daily


def test_combination_uses_only_common_dates_from_common_interval_start():
    first = [
        {"date": "2026-01-01", "index_return": 0.10, "start_return": 0.10},
        {"date": "2026-01-02", "index_return": 0.21, "start_return": 0.21},
    ]
    second = [
        {"date": "2026-01-02", "index_return": 0.20, "start_return": 0.20},
        {"date": "2026-01-03", "index_return": 0.44, "start_return": 0.44},
    ]
    products = [{"returns": first, "ratio": "50"}, {"returns": second, "ratio": "50"}]
    combined = combine_product_returns(products)
    # 共同日期只有 2026-01-02；组合从共同区间起点 1.0 还原，不引用区间外净值。
    assert [row["date"] for row in combined] == ["2026-01-02"]
    assert combined[-1]["start_return"] == pytest.approx(0.205)
