from types import SimpleNamespace

import pandas as pd

from app.services.strategy_backtest_report_service import StrategyBacktestReportService


def test_normalized_weights_allows_percentage_total_other_than_100():
    weights = StrategyBacktestReportService._normalized_weights([
        {"ratio": "70"},
        {"ratio": "30"},
        {"ratio": "3"},
    ])

    assert weights == [0.7, 0.3, 0.03]


def test_single_product_report_defaults_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {"products": [], "weight_allocation": None})()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["单品", "", "100.00%"]]


def test_single_product_report_defaults_missing_product_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "SCHD.US", "product_name": "SCHD.US"}],
        "weight_allocation": None,
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["SCHD.US", "SCHD.US", "100.00%"]]


def test_weight_allocation_adds_percent_suffix():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "600519", "product_name": "贵州茅台", "ratio": "100"}],
        "weight_allocation": None,
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["600519", "贵州茅台", "100%"]]


def test_return_section_marks_rolling_returns_unavailable_before_five_years():
    dates = pd.to_datetime(["2023-01-31", "2023-02-28"])
    result = SimpleNamespace(
        index_df=pd.DataFrame({"date": dates, "index_return": [0.01, 0.02], "net_value": [1.01, 1.02]}),
        start_df=pd.DataFrame({"date": dates, "start_return": [0.02, 0.03], "net_value": [1.02, 1.03]}),
    )
    metrics = {
        "index_rolling_return_3": {
            "status": "failed",
            "reason": "数据不足5年，当前仅3.1年",
            "total_months": 37,
            "total_years": 37 / 12,
        },
        "excess_rolling_return_3": {
            "status": "failed",
            "reason": "数据不足5年，当前仅3.1年",
            "total_months": 37,
            "total_years": 37 / 12,
        },
    }

    section = StrategyBacktestReportService()._return_section(metrics, result)
    rolling_rows = section[2]["table"]["rows"]

    assert rolling_rows == [
        ["3个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
        ["6个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
        ["12个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
    ]
    excess_rows = StrategyBacktestReportService()._excess_section(metrics, result)[2]["table"]["rows"]
    assert excess_rows == [
        ["1个月（数据不足5年，当前仅3.1年）", "-", "-"],
        ["3个月（数据不足5年，当前仅3.1年）", "-", "-"],
        ["6个月（数据不足5年，当前仅3.1年）", "-", "-"],
        ["12个月（数据不足5年，当前仅3.1年）", "-", "-"],
    ]
