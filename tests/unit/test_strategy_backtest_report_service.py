from types import SimpleNamespace

import pandas as pd
import pytest

import app.services.strategy_backtest_report_service as report_module
from app.services.strategy_backtest_report_service import StrategyBacktestReportService


def test_single_product_report_defaults_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {"products": [], "weight_allocation": None, "index_stock_code": []})()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["单品", "", "100.00%", "-"]]


def test_single_product_report_defaults_missing_product_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "SCHD.US", "product_name": "SCHD.US"}],
        "weight_allocation": None,
        "index_stock_code": [],
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["SCHD.US", "SCHD.US", "100.00%", "-"]]


def test_weight_allocation_adds_percent_suffix():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "600519", "product_name": "贵州茅台", "ratio": "100"}],
        "weight_allocation": None,
        "index_stock_code": [],
    })()

    allocation = service._weight_allocation(request, "RPT-S")

    assert allocation["rows"] == [["600519", "贵州茅台", "100%", "-"]]


def test_weight_allocation_drops_zero_ratio_products():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "SOXX", "product_name": "半导体ETF", "ratio": "0"},
        ],
        "weight_allocation": None,
        "index_stock_code": [],
    })()

    allocation = service._weight_allocation(request, "RPT-M")

    assert allocation["rows"] == [["600519", "贵州茅台", "50%", "-"]]


def test_weight_allocation_fills_average_volume_by_code_label():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "0700.HK", "product_name": "腾讯控股", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_stock_code": ["0700.HK"],
    })()

    allocation = service._weight_allocation(request, "RPT-M", {"600519": "2,000,000", "0700.HK (指数)": "5,000,000"})

    assert allocation["rows"] == [
        ["600519", "贵州茅台", "50%", "2,000,000"],
        ["0700.HK (指数)", "腾讯控股", "50%", "5,000,000"],
    ]


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


def test_weight_allocation_marks_selected_index_from_list():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "AAA.US", "product_name": "A", "ratio": "50"},
            {"stock_code": "BBB.US", "product_name": "B", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_stock_code": ["BBB.US"],
    })()

    allocation = service._weight_allocation(request, "RPT-M")

    assert allocation["rows"] == [
        ["AAA.US", "A", "50%", "-"],
        ["BBB.US (指数)", "B", "50%", "-"],
    ]


def test_resolve_returns_injects_benchmark_index_by_date(monkeypatch):
    """指数注入按日期对齐：组合独有日期保留默认基准，修复按位 zip 的日历错位。"""
    service = StrategyBacktestReportService()
    combined = [
        {"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10},
        {"date": "2024-01-03", "index_return": 0.40, "start_return": 0.12},
    ]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "index_stock_code": ["0700.HK"],
        "products": [{
            "stock_code": "0700.HK",
            "returns": [
                {"date": "2024-01-01", "index_return": 0.10, "start_return": 0.01},
                {"date": "2024-01-02", "index_return": 0.20, "start_return": 0.02},
            ],
        }],
    })()

    data = service._resolve_returns(request)

    assert data[0]["index_return"] == 0.20
    assert data[1]["index_return"] == 0.40


def test_resolve_returns_interim_uses_first_selected_benchmark(monkeypatch):
    """多基准组装交付前，多选暂取首个选中项渲染。"""
    service = StrategyBacktestReportService()
    combined = [{"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10}]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "index_stock_code": ["AAA.US", "BBB.US"],
        "products": [
            {"stock_code": "AAA.US", "returns": [{"date": "2024-01-02", "index_return": 0.11, "start_return": 0.01}]},
            {"stock_code": "BBB.US", "returns": [{"date": "2024-01-02", "index_return": 0.22, "start_return": 0.02}]},
        ],
    })()

    data = service._resolve_returns(request)

    assert data[0]["index_return"] == 0.11


class _StubKlineService:
    def __init__(self, rows=None, error=None):
        self.rows = rows if rows is not None else []
        self.error = error
        self.calls = []

    def get_kline_data(self, stock_code, market_type, limit, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append({"stock_code": stock_code, "market_type": market_type, "limit": limit, **kwargs})
        return self.rows


def _pearson(left, right):
    count = len(left)
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    cov = sum((x - mean_left) * (y - mean_right) for x, y in zip(left, right))
    var_left = sum((x - mean_left) ** 2 for x in left)
    var_right = sum((y - mean_right) ** 2 for y in right)
    return cov / (var_left * var_right) ** 0.5


def _cumulative_from_daily(daily):
    cumulative = []
    current = 0.0
    for value in daily:
        current = (1 + value) * (1 + current) - 1
        cumulative.append(current)
    return cumulative


def _cumulative_product(stock_code, product_name, ratio, daily, market_type=None):
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
    product = {
        "stock_code": stock_code,
        "product_name": product_name,
        "ratio": ratio,
        "returns": [
            {"date": date, "index_return": 0.0, "start_return": value}
            for date, value in zip(dates, _cumulative_from_daily(daily))
        ],
    }
    if market_type:
        product["market_type"] = market_type
    return product


def _correlation_request(products, index_stock_code=None, report_type="RPT-M"):
    return type("Request", (), {
        "products": products,
        "index_stock_code": index_stock_code,
        "report_type": report_type,
    })()


def test_correlation_matrix_computes_lower_triangle_and_mirrors(monkeypatch):
    daily_a = [0.01, 0.02, -0.015, 0.005]
    daily_b = [0.005, -0.01, 0.03, -0.002]
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", daily_a),
        _cumulative_product("0700.HK", "腾讯控股", "50", daily_b, market_type="hk"),
    ], index_stock_code=["0700.HK"])
    result = SimpleNamespace(index_df=pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
    }))

    correlation = StrategyBacktestReportService()._correlation_matrix(request, result)

    # 对齐轴上首日收益从净值 1.0 还原，还原序列与输入日涨跌幅一致。
    pair_value = pytest.approx(_pearson(daily_a, daily_b))
    assert correlation["labels"] == ["600519.SS", "0700.HK (指数)"]
    assert correlation["matrix"] == [
        [1.0, pair_value],
        [pair_value, 1.0],
    ]


def test_correlation_matrix_marks_unavailable_pairs_as_none():
    # 字面十进制累计值保证常数序列经 Decimal 还原后仍精确相等。
    request = _correlation_request([
        {"stock_code": "600519.SS", "product_name": "贵州茅台", "ratio": "60", "returns": [
            {"date": "2024-01-01", "index_return": 0.0, "start_return": 0.0},
            {"date": "2024-01-02", "index_return": 0.0, "start_return": 0.1},
            {"date": "2024-01-03", "index_return": 0.0, "start_return": 0.045},
        ]},
        {"stock_code": "BHP.AX", "product_name": "必和必拓", "ratio": "40", "market_type": "au", "returns": [
            {"date": "2024-01-01", "index_return": 0.0, "start_return": 0.02},
            {"date": "2024-01-02", "index_return": 0.0, "start_return": 0.0404},
            {"date": "2024-01-03", "index_return": 0.0, "start_return": 0.061208},
        ]},
    ])
    result = SimpleNamespace(index_df=pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    }))

    correlation = StrategyBacktestReportService()._correlation_matrix(request, result)

    # 常数日涨跌幅方差为 0，相关系数不可计算，热力图按缺数据显示。
    assert correlation["matrix"] == [
        [1.0, None],
        [None, 1.0],
    ]


def test_correlation_matrix_skipped_for_single_product():
    request = _correlation_request([
        _cumulative_product("SCHD.US", "SCHD", "", [0.01, 0.01, 0.01], market_type="en"),
    ], report_type="RPT-S")
    result = SimpleNamespace(index_df=pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
    }))

    assert StrategyBacktestReportService()._correlation_matrix(request, result) is None


def test_correlation_matrix_skipped_without_products():
    request = _correlation_request([])
    result = SimpleNamespace(index_df=pd.DataFrame({"date": pd.to_datetime(["2024-01-01"])}))

    assert StrategyBacktestReportService()._correlation_matrix(request, result) is None


def test_product_volumes_passes_market_type_and_formats_average(monkeypatch):
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", [0.01, 0.02, -0.015, 0.005]),
        _cumulative_product("0700.HK", "腾讯控股", "50", [0.005, -0.01, 0.03, -0.002], market_type="hk"),
    ])
    result = SimpleNamespace(index_df=pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
    }))
    stub = _StubKlineService(rows=[{"volume": 1_000_000}, {"volume": 3_000_000}])
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: stub)

    volumes = StrategyBacktestReportService()._product_volumes(request, "2024-01-01", "2024-01-04")

    assert volumes == {"600519.SS": "2,000,000", "0700.HK": "2,000,000"}
    assert [(call["stock_code"], call["market_type"], call["start_date"], call["end_date"]) for call in stub.calls] == [
        ("600519.SS", "cn", "2024-01-01", "2024-01-04"),
        ("0700.HK", "hk", "2024-01-01", "2024-01-04"),
    ]


def test_product_volumes_degrades_to_dash_when_kline_fails(monkeypatch):
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", [0.01, 0.02, -0.015, 0.005]),
    ])
    result = SimpleNamespace(index_df=pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
    }))
    stub = _StubKlineService(error=RuntimeError("kline unavailable"))
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: stub)

    volumes = StrategyBacktestReportService()._product_volumes(request, "2024-01-01", "2024-01-04")

    assert volumes == {"600519.SS": "-"}

