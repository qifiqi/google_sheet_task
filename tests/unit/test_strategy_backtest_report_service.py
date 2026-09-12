from types import SimpleNamespace

import pandas as pd

from app.services.strategy_backtest_report_service import StrategyBacktestReportService


def test_single_product_report_defaults_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {"products": [], "weight_allocation": None, "index_stock_code": None})()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["单品", "", "100.00%"]]


def test_single_product_report_defaults_missing_product_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "SCHD.US", "product_name": "SCHD.US"}],
        "weight_allocation": None,
        "index_stock_code": None,
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["SCHD.US", "SCHD.US", "100.00%"]]


def test_weight_allocation_adds_percent_suffix():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "600519", "product_name": "贵州茅台", "ratio": "100"}],
        "weight_allocation": None,
        "index_stock_code": None,
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["600519", "贵州茅台", "100%"]]


def test_weight_allocation_drops_zero_ratio_products():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "SOXX", "product_name": "半导体ETF", "ratio": "0"},
        ],
        "weight_allocation": None,
        "index_stock_code": None,
    })()

    allocation = service._weight_allocation(request, "RPT-M")

    assert allocation["rows"] == [["600519", "贵州茅台", "50%"]]


def _filename_request(report_type, products):
    return type("Request", (), {"products": products, "report_type": report_type})()


def test_default_filename_downgrades_to_rpt_s_when_single_active_product():
    service = StrategyBacktestReportService()
    request = _filename_request("RPT-M", [
        {"stock_code": "600519", "ratio": "0"},
        {"stock_code": "soxx.us", "ratio": "100"},
        {"stock_code": "SCHD.US", "ratio": "0%"},
    ])

    filename = service._default_filename(request)

    assert filename.startswith("RPT-S-SOXX.US-")
    assert "600519" not in filename and "SCHD.US" not in filename


def test_default_filename_keeps_rpt_m_with_multiple_active_products():
    service = StrategyBacktestReportService()
    request = _filename_request("RPT-M", [
        {"stock_code": "600519", "ratio": "50"},
        {"stock_code": "SOXX.US", "ratio": "0"},
        {"stock_code": "SCHD.US", "ratio": "50"},
    ])

    filename = service._default_filename(request)

    assert filename.startswith("RPT-M-600519-SCHD.US-")
    assert "SOXX.US" not in filename


def test_return_section_marks_rolling_returns_unavailable_before_five_years():
    dates = pd.to_datetime(["2023-01-31", "2023-02-28"])
    result = SimpleNamespace(
        index_df=pd.DataFrame({"date": dates, "index_return": [0.01, 0.02], "net_value": [1.01, 1.02]}),
        start_df=pd.DataFrame({"date": dates, "start_return": [0.02, 0.03], "net_value": [1.02, 1.03]}),
    )
    reason = {
        "status": "failed",
        "reason": "数据不足5年，当前仅3.1年",
        "total_months": 37,
        "total_years": 37 / 12,
    }
    metrics = {
        **{
            f"rolling_return_{months}_reason": reason["reason"]
            for months in (3, 6, 12)
        },
        **{
            f"excess_rolling_return_{months}_reason": reason["reason"]
            for months in (3, 6, 12)
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
        # 1 个月窗口没有 V1 滚动序列，且无月度超额数据时显示占位。
        ["1个月", "-", "-"],
        ["3个月（数据不足5年，当前仅3.1年）", "-", "-"],
        ["6个月（数据不足5年，当前仅3.1年）", "-", "-"],
        ["12个月（数据不足5年，当前仅3.1年）", "-", "-"],
    ]
