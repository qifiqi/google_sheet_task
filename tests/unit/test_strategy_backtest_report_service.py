from types import SimpleNamespace

import pandas as pd
import pytest

import app.services.strategy_backtest_report_service as report_module
from app.services.strategy_backtest_report_service import StrategyBacktestReportService


def _entry(code, ratio=100):
    """基准条目 duck 对象（Schema 归一后的形态：stock_code + ratio%）。"""
    return SimpleNamespace(stock_code=code, ratio=ratio)


def test_single_product_report_defaults_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {"products": [], "weight_allocation": None, "index_benchmarks": []})()

    blocks = service._weight_allocation_blocks(request, "RPT-S")

    assert [block["title"] for block in blocks] == ["策略权重"]
    assert blocks[0]["rows"] == [["单品", "", "100.00%", "-", "-"]]


def test_single_product_report_defaults_missing_product_weight_to_100_percent():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "SCHD.US", "product_name": "SCHD.US"}],
        "weight_allocation": None,
        "index_benchmarks": [],
    })()

    blocks = service._weight_allocation_blocks(request, "RPT-S")

    assert blocks[0]["rows"] == [["SCHD.US", "SCHD.US", "100.00%", "-", "-"]]


def test_weight_allocation_adds_percent_suffix():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "600519", "product_name": "贵州茅台", "ratio": "100"}],
        "weight_allocation": None,
        "index_benchmarks": [],
    })()

    blocks = service._weight_allocation_blocks(request, "RPT-S")

    assert blocks[0]["rows"] == [["600519", "贵州茅台", "100%", "-", "-"]]


def test_weight_allocation_drops_zero_ratio_products():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "SOXX", "product_name": "半导体ETF", "ratio": "0"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [],
    })()

    blocks = service._weight_allocation_blocks(request, "RPT-M")

    assert blocks[0]["rows"] == [["600519", "贵州茅台", "50%", "-", "-"]]


def test_etf_total_assets_detail_abbreviates_large_values(monkeypatch):
    """资产总数按中文习惯缩写（亿/万），避免长数字撑爆表格列宽。"""
    cases = [
        (488981004288, "4889.81亿"),
        (48898100, "4889.81万"),
        (85000, "8.50万"),
        (9999, "9,999"),
        (None, "-"),
    ]
    for value, expected in cases:
        monkeypatch.setattr(report_module, "get_etf_total_assets_detail", lambda *a, _v=value, **k: (_v, True))
        assert StrategyBacktestReportService._etf_total_assets_detail({"stock_code": "QQQ.US"}) == (expected, True)


def test_weight_allocation_fills_etf_total_assets_column():
    """资产总数列按代码标签回填；未提供的标的显示 "-"。"""
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "0700.HK", "product_name": "腾讯控股", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [],
    })()

    blocks = service._weight_allocation_blocks(
        request, "RPT-M",
        amounts={"600519": "10.00亿", "0700.HK": "300.00亿"},
        assets={"600519": "1,234,567,890"},
    )

    assert blocks[0]["columns"] == ["股票代码", "股票名", "权重", "平均成交额 (半年)", "ETF资产总数"]
    assert blocks[0]["rows"] == [
        ["600519", "贵州茅台", "50%", "10.00亿", "1,234,567,890"],
        ["0700.HK", "腾讯控股", "50%", "300.00亿", "-"],
    ]


def test_weight_allocation_uses_net_asset_header_when_all_stocks():
    """全部为个股（无任何 ETF 资产值）时，资产列头改为 净资产。"""
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [{"stock_code": "AAPL.US", "product_name": "苹果", "ratio": "100"}],
        "weight_allocation": None,
        "index_benchmarks": [],
    })()

    blocks = service._weight_allocation_blocks(
        request, "RPT-S", assets_header="净资产",
    )

    assert blocks[0]["columns"] == ["股票代码", "股票名", "权重", "平均成交额 (半年)", "净资产"]


def test_weight_allocation_fills_average_amount_by_code_label():
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "600519", "product_name": "贵州茅台", "ratio": "50"},
            {"stock_code": "0700.HK", "product_name": "腾讯控股", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [_entry("0700.HK")],
    })()

    blocks = service._weight_allocation_blocks(
        request, "RPT-M", {"600519": "10.00亿", "0700.HK (指数)": "150.00亿"}
    )

    assert [block["title"] for block in blocks] == ["策略权重", "指数权重"]
    assert blocks[0]["rows"] == [
        ["600519", "贵州茅台", "50%", "10.00亿", "-"],
        ["0700.HK", "腾讯控股", "50%", "-", "-"],
    ]
    # 指数表代码列不再重复 "(指数)" 后缀。
    assert blocks[1]["rows"] == [
        ["0700.HK", "腾讯控股", "100%", "150.00亿", "-"],
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

    # 权重为百分比数字但不带 % 后缀：裸 % 会让前端 decodeURIComponent 抛 URI malformed。
    assert filename.startswith("RPT-M-600519_50-SCHD.US_50-")
    assert "SOXX.US" not in filename
    assert "%" not in filename and "(" not in filename


def test_default_filename_weight_supports_percent_and_decimal_ratios():
    service = StrategyBacktestReportService()
    request = _filename_request("RPT-M", [
        {"stock_code": "510300", "ratio": "33.33%"},
        {"stock_code": "510500", "ratio": 0.665},
        {"stock_code": "510800"},
    ])

    filename = service._default_filename(request)

    # 百分比/小数比例统一折算为百分比数字；缺失比例只拼代码。
    assert filename.startswith("RPT-M-510300_33.33-510500_66.5-510800-")


def test_default_filename_falls_back_to_codes_when_weighted_name_too_long():
    service = StrategyBacktestReportService()
    request = _filename_request("RPT-M", [
        {"stock_code": f"6005{i:02}.SH", "ratio": "10"}
        for i in range(20)
    ])

    filename = service._default_filename(request)

    # 加权形式超长时回落纯代码，保护 Windows 路径长度限制。
    assert filename.startswith("RPT-M-600500.SH-")
    assert "(" not in filename


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

    runs = [SimpleNamespace(code=None, label="指数", result=SimpleNamespace(metrics=metrics, index_df=result.index_df))]

    section = StrategyBacktestReportService()._return_section(runs)
    rolling_rows = section[2]["table"]["rows"]

    assert rolling_rows == [
        ["3个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
        ["6个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
        ["12个月滚动（数据不足5年，当前仅3.1年）", "-", "-", "-"],
    ]
    excess_rows = StrategyBacktestReportService()._excess_section(runs)[2]["table"]["rows"]
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
        "index_benchmarks": [_entry("BBB.US")],
    })()

    blocks = service._weight_allocation_blocks(request, "RPT-M")

    assert blocks[0]["rows"] == [
        ["AAA.US", "A", "50%", "-", "-"],
        ["BBB.US", "B", "50%", "-", "-"],
    ]
    assert blocks[1]["rows"] == [
        ["BBB.US", "B", "100%", "-", "-"],
    ]


class _StubAnalyzer:
    """记录引擎入参并返回占位结果，用于断言 runs 构建的轴对齐与循环次数。"""

    def __init__(self):
        self.calls = []

    def get_calculate_metrics_v1_with_dataframes(self, rows, runtime=None):
        self.calls.append(rows)
        return SimpleNamespace(
            metrics={},
            index_df=pd.DataFrame({"date": pd.to_datetime([row["date"] for row in rows])}),
        )


def test_build_benchmark_runs_intersects_axis_and_injects_per_benchmark(monkeypatch):
    """统一日期轴 = 组合日期 ∩ 基准日期；基准缺失的交易日整行剔除。"""
    service = StrategyBacktestReportService()
    combined = [
        {"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10},
        {"date": "2024-01-03", "index_return": 0.40, "start_return": 0.12},
        {"date": "2024-01-06", "index_return": 0.50, "start_return": 0.15},
    ]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [_entry("0700.HK")],
        "include_composite_benchmark": False,
        "products": [{
            "stock_code": "0700.HK",
            "returns": [
                {"date": "2024-01-01", "index_return": 0.10, "start_return": 0.01},
                {"date": "2024-01-02", "index_return": 0.20, "start_return": 0.02},
                {"date": "2024-01-06", "index_return": 0.25, "start_return": 0.03},
            ],
        }],
    })()

    runs = service._build_benchmark_runs(request)

    assert [row["date"] for row in stub.calls[0]] == ["2024-01-02", "2024-01-06"]
    assert [row["index_return"] for row in stub.calls[0]] == [0.20, 0.25]
    assert [row["start_return"] for row in stub.calls[0]] == [0.10, 0.15]
    assert runs[0].label == "指数"


def test_build_benchmark_runs_runs_engine_once_per_selected_benchmark(monkeypatch):
    """多选逐基准运行引擎，标签用 指数(代码 比例%) 自描述；策略列各次运行一致。"""
    service = StrategyBacktestReportService()
    combined = [{"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10}]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [_entry("AAA.US"), _entry("BBB.US")],
        "include_composite_benchmark": False,
        "products": [
            {"stock_code": "AAA.US", "returns": [{"date": "2024-01-02", "index_return": 0.11, "start_return": 0.01}]},
            {"stock_code": "BBB.US", "returns": [{"date": "2024-01-02", "index_return": 0.22, "start_return": 0.02}]},
        ],
    })()

    runs = service._build_benchmark_runs(request)

    assert len(stub.calls) == 2
    assert [run.label for run in runs] == ["指数(AAA.US 100%)", "指数(BBB.US 100%)"]
    assert stub.calls[0][0]["index_return"] == 0.11


def test_build_benchmark_runs_includes_composite_by_default(monkeypatch):
    """组合指数开关默认开启：组合列在前且列头为无标记的"指数"。

    自定义满配单条本会得到裸"指数"列头，与组合列撞名时改用 指数(代码) 消歧。
    """
    service = StrategyBacktestReportService()
    combined = [{"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10}]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [_entry("0700.HK")],
        "products": [{
            "stock_code": "0700.HK",
            "returns": [{"date": "2024-01-02", "index_return": 0.20, "start_return": 0.02}],
        }],
    })()

    runs = service._build_benchmark_runs(request)

    assert [run.label for run in runs] == ["指数", "指数(0700.HK)"]
    assert runs[0].code is None and runs[1].code == "0700.HK"
    # 组合列吃原始组合收益（index_return=0.30），自定义列吃注入缩放序列（0.20）。
    assert stub.calls[0][0]["index_return"] == 0.30
    assert stub.calls[1][0]["index_return"] == 0.20
    # start_return 两列都用组合收益（策略指标各次运行一致）。
    assert stub.calls[0][0]["start_return"] == stub.calls[1][0]["start_return"] == 0.10


def test_build_benchmark_runs_composite_falls_back_when_disabled_without_custom(monkeypatch):
    """开关关闭且未选自定义指数时回落组合指数，保证报告恒有基准。"""
    service = StrategyBacktestReportService()
    combined = [{"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10}]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [],
        "include_composite_benchmark": False,
        "products": [],
    })()

    runs = service._build_benchmark_runs(request)

    assert [run.label for run in runs] == ["指数"]
    assert runs[0].code is None
    assert len(stub.calls) == 1


def test_build_benchmark_runs_scales_benchmark_by_ratio(monkeypatch):
    """比例缩放口径 = 比例×日收益再复利（等价 比例×指数+现金）。"""
    service = StrategyBacktestReportService()
    combined = [
        {"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10},
        {"date": "2024-01-03", "index_return": 0.40, "start_return": 0.12},
    ]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [_entry("QQQ.US", ratio=50)],
        "include_composite_benchmark": False,
        "products": [{
            "stock_code": "QQQ.US",
            "returns": [
                {"date": "2024-01-02", "index_return": 0.10, "start_return": 0.01},
                {"date": "2024-01-03", "index_return": 0.20, "start_return": 0.02},
            ],
        }],
    })()

    runs = service._build_benchmark_runs(request)

    # 满配日收益 10%/18.18% → 半仓 5%/9.09% → 复利累计 5%/14.77%。
    scaled = stub.calls[0]
    assert scaled[0]["index_return"] == pytest.approx(0.05)
    assert scaled[1]["index_return"] == pytest.approx((1 + 0.05) * (1 + 0.5 * (1.2 / 1.1 - 1)) - 1)
    # 单条基准但非满配：标签带比例，避免误读为原始指数。
    assert runs[0].label == "指数(50%)"


def test_build_benchmark_runs_allows_same_product_at_different_ratios(monkeypatch):
    """同一产品不同比例是两条独立基准（语义 A 的核心诉求）。"""
    service = StrategyBacktestReportService()
    combined = [{"date": "2024-01-02", "index_return": 0.30, "start_return": 0.10}]
    monkeypatch.setattr(service, "_combine_product_returns", lambda request: combined)
    stub = _StubAnalyzer()
    monkeypatch.setattr(report_module, "performance_analyzer", stub)
    request = type("Request", (), {
        "report_type": "RPT-M",
        "runtime_params": {},
        "index_benchmarks": [_entry("QQQ.US", ratio=50), _entry("QQQ.US", ratio=100)],
        "include_composite_benchmark": False,
        "products": [{
            "stock_code": "QQQ.US",
            "returns": [{"date": "2024-01-02", "index_return": 0.10, "start_return": 0.01}],
        }],
    })()

    runs = service._build_benchmark_runs(request)

    assert len(stub.calls) == 2
    # 同股不同比例：列头只展示比例，不再重复代码。
    assert [run.label for run in runs] == ["指数(50%)", "指数(100%)"]
    assert stub.calls[0][0]["index_return"] == pytest.approx(0.05)
    assert stub.calls[1][0]["index_return"] == 0.10


def test_weight_allocation_shows_strategy_rows_and_index_ratio_rows():
    """策略表 = 策略权重；指数表 = 指数自身的比例权重（真实值）。

    策略比例为 0 的产品不进入策略行；被选为指数的标的按其比例权重
    展示在指数表（含与策略同股的情况，如 QQQ 30% 与 QQQ 100%）。
    """
    service = StrategyBacktestReportService()
    request = type("Request", (), {
        "products": [
            {"stock_code": "QQQ.US", "product_name": "纳指ETF", "ratio": "30"},
            {"stock_code": "SOXX.US", "product_name": "半导体ETF", "ratio": "0"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [_entry("QQQ.US"), _entry("SOXX.US", 30)],
    })()

    blocks = service._weight_allocation_blocks(request, "RPT-M")

    assert blocks[0]["title"] == "策略权重"
    assert blocks[0]["rows"] == [
        ["QQQ.US", "纳指ETF", "30%", "-", "-"],
    ]
    assert blocks[1]["title"] == "指数权重"
    assert blocks[1]["rows"] == [
        ["QQQ.US", "纳指ETF", "100%", "-", "-"],
        ["SOXX.US", "半导体ETF", "30%", "-", "-"],
    ]


def test_return_section_expands_columns_per_benchmark():
    runs = [
        SimpleNamespace(code="AAA.US", weight=1, label="指数(AAA.US 100%)", result=SimpleNamespace(metrics={
            "index_cumulative_return": 0.10, "start_cumulative_return": 0.30,
            "excess_cumulative_return": 0.20})),
        SimpleNamespace(code="BBB.US", weight=0.3, label="指数(BBB.US 30%)", result=SimpleNamespace(metrics={
            "index_cumulative_return": 0.05, "start_cumulative_return": 0.30,
            "excess_cumulative_return": 0.25})),
    ]

    core = StrategyBacktestReportService()._return_section(runs)[0]["table"]

    assert core["columns"] == ["指标", "指数(AAA.US 100%)", "指数(BBB.US 30%)", "策略",
                               "超额(AAA.US 100%)", "超额(BBB.US 30%)"]
    assert core["rows"][0] == ["累计回报率", "10.00%", "5.00%", "30.00%", "20.00%", "25.00%"]


def test_excess_headers_follow_same_code_ratio_rule():
    """同股不同比例只展示比例；异股展示 代码 比例%，与指数列头对称。"""
    service = StrategyBacktestReportService()
    runs_same = [SimpleNamespace(code="QQQ.US", weight=0.5, label="指数(50%)"),
                 SimpleNamespace(code="QQQ.US", weight=1, label="指数(100%)")]
    runs_mixed = [SimpleNamespace(code="QQQ.US", weight=1, label="指数(QQQ.US 100%)"),
                  SimpleNamespace(code="SOXX.US", weight=0.3, label="指数(SOXX.US 30%)")]

    assert service._excess_headers(runs_same) == ["超额(50%)", "超额(100%)"]
    assert service._excess_headers(runs_mixed) == ["超额(QQQ.US 100%)", "超额(SOXX.US 30%)"]
    assert service._excess_headers(runs_same[:1]) == ["超额(策略-指数)"]


def test_excess_headers_omit_marker_for_composite_run():
    """组合指数的派生列头不带任何标记：超额列为裸"超额"，与"指数"列头对称。"""
    service = StrategyBacktestReportService()
    runs = [SimpleNamespace(code=None, weight=1, label="指数"),
            SimpleNamespace(code="QQQ.US", weight=1, label="指数(QQQ.US)")]

    assert service._excess_headers(runs) == ["超额", "超额(QQQ.US)"]
    assert service._tagged_header("超额回撤", runs, runs[0]) == "超额回撤"
    assert service._tagged_header("月数", runs, runs[0]) == "月数"
    # 胜率列的"跑赢"宾语不能省略，组合指数固定表述为"跑赢组合"。
    assert service._benchmark_tag(runs, runs[0]) == ""
    assert f"策略胜率(跑赢{service._benchmark_tag(runs, runs[0]) or '组合'})" == "策略胜率(跑赢组合)"


def test_risk_adjusted_section_splits_excess_rows_per_benchmark():
    runs = [
        SimpleNamespace(code="AAA.US", weight=1, label="指数(AAA.US 100%)", result=SimpleNamespace(metrics={
            "excess_sharpe": 0.5, "excess_sortino": 0.7})),
        SimpleNamespace(code="BBB.US", weight=0.3, label="指数(BBB.US 30%)", result=SimpleNamespace(metrics={
            "excess_sharpe": 0.6, "excess_sortino": 0.8})),
    ]

    table = StrategyBacktestReportService()._risk_adjusted_section(runs)[0]["table"]

    assert table["columns"] == ["指标", "指数(AAA.US 100%)", "指数(BBB.US 30%)", "策略"]
    assert [row[0] for row in table["rows"]] == [
        "夏普比率", "卡玛比率", "索提诺比率",
        "超额夏普比率(AAA.US 100%)", "超额索提诺比率(AAA.US 100%)",
        "超额夏普比率(BBB.US 30%)", "超额索提诺比率(BBB.US 30%)",
    ]
    # 超额行的指数列占位随基准数补足，行宽与列数严格一致。
    assert all(len(row) == 4 for row in table["rows"])


def _rich_metrics(tag: float) -> dict:
    """覆盖八章全部消费键的 V1 指标字典；数值按 tag 区分各基准。"""

    def yearly(field, value):
        return [{"year": "2024", field: value}, {"year": "all", field: value}]

    return {
        "index_cumulative_return": 0.10 + tag, "start_cumulative_return": 0.30,
        "excess_cumulative_return": 0.20 - tag,
        "index_annualized_rates": yearly("annualized_return", 0.10 + tag),
        "start_annualized_rates": yearly("annualized_return", 0.30),
        "index_sharpe_ratios": yearly("sharpe_ratio", 0.5 + tag) + yearly("annual_std_dev", 0.2)
                               + yearly("avg_monthly_return", 0.01) + yearly("monthly_std_dev", 0.03),
        "start_sharpe_ratios": yearly("sharpe_ratio", 0.9) + yearly("annual_std_dev", 0.25)
                               + yearly("avg_monthly_return", 0.02) + yearly("monthly_std_dev", 0.04),
        "index_kama_ratio": yearly("kama_ratio", 0.6 + tag),
        "start_kama_ratio": yearly("kama_ratio", 0.8),
        "index_sortino_ratio": yearly("sortino_ratio", 0.7 + tag),
        "start_sortino_ratio": yearly("sortino_ratio", 0.9),
        "index_returns_rate": yearly("annual_return", 0.12 + tag),
        "start_returns_rate": yearly("annual_return", 0.32),
        "index_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": 0.15 + tag},
                                   "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.15 + tag}]},
        "start_maximum_drawdown": {"total_maximum_drawdown": {"drawdown": 0.10},
                                   "year_maximum_drawdown": [{"year": "2024", "drawdown": 0.10}]},
        "year_index_yearly_max_repair_days": {"2024": 5},
        "year_start_yearly_max_repair_days": {"2024": 3},
        "daily_drawdown_threshold": 0.02,
        "index_dd_count": 4, "start_dd_count": 2,
        "excess_sharpe": 0.4 + tag, "excess_sortino": 0.5 + tag,
        "index_monthly_distribution": [1, 2, 3, 4, 5, 6, 7],
        "index_monthly_distribution_pct": [5, 10, 15, 20, 25, 15, 10],
        "start_monthly_distribution": [2, 2, 2, 2, 2, 2, 2],
        "start_monthly_distribution_pct": [10, 10, 10, 10, 10, 10, 40],
        "total_months": 12,
        "index_profit_months": 8, "start_profit_months": 9,
        "index_loss_months": 4, "start_loss_months": 3,
        "index_profit_percentage": 0.66, "start_profit_percentage": 0.75,
        "index_max_monthly_return": 0.05, "start_max_monthly_return": 0.06,
        "index_max_monthly_loss": -0.03, "start_max_monthly_loss": -0.02,
        "index_monthly_return_skewness": 0.1 + tag, "start_monthly_return_skewness": 0.2,
        "index_monthly_return_kurtosis": 0.3, "start_monthly_return_kurtosis": 0.4,
        "index_days_distribution": [10, 20, 30, 40, 50, 60, 70, 80],
        "index_days_distribution_pct": [5, 10, 10, 15, 15, 15, 15, 15],
        "start_days_distribution": [5, 5, 5, 5, 5, 5, 5, 5],
        "start_days_distribution_pct": [10, 10, 10, 10, 10, 10, 20, 20],
        "total_trading_days": 240,
        "index_profit_days": 130, "start_profit_days": 140,
        "index_loss_days": 110, "start_loss_days": 100,
        "index_days_profit_percentage": 0.54, "start_days_profit_percentage": 0.58,
        "index_mean_daily_return": 0.0005, "start_mean_daily_return": 0.0008,
        "index_daily_return_std": 0.01, "start_daily_return_std": 0.012,
        "index_max_daily_gain": 0.03, "start_max_daily_gain": 0.035,
        "index_max_daily_loss": -0.025, "start_max_daily_loss": -0.02,
        "index_mean_daily_skewness": 0.05, "start_mean_daily_skewness": 0.06,
        "index_mean_daily_kurtosis": 0.07, "start_mean_daily_kurtosis": 0.08,
        "index_avg_profit_day_return": 0.01, "start_avg_profit_day_return": 0.012,
        "index_avg_loss_day_return": -0.009, "start_avg_loss_day_return": -0.008,
        "index_profit_loss_ratio": 1.1, "start_profit_loss_ratio": 1.3,
        "index_max_profit_loss_ratio": 8.0, "start_max_profit_loss_ratio": 9.0,
        "excess_returns": yearly("annualized_return_diff", 0.18 - tag),
        "excess_distribution": [1, 2, 3, 4, 5],
        "excess_distribution_pct": [10, 20, 30, 20, 20],
        "average_monthly_excess_return": 0.004,
        "monthly_excess_return_standard_deviation": 0.02,
        "monthly_excess_win_rate": 0.6,
        "max_monthly_excess": 0.03,
        "excess_rolling_return_3_avg_return": 0.003, "excess_rolling_return_3_win_rate": 0.55,
        "excess_rolling_return_6_avg_return": 0.004, "excess_rolling_return_6_win_rate": 0.6,
        "excess_rolling_return_12_avg_return": 0.005, "excess_rolling_return_12_win_rate": 0.65,
        "market_downturn_threshold": -0.05, "market_upturn_threshold": 0.05,
        "daily_extreme_threshold": 0.03,
        "index_downfall_months_len": 6, "start_downfall_months_len": 6,
        "index_downfall_avg_return": -0.03, "start_downfall_avg_return": -0.01,
        "downfall_excess_avg_return": 0.02, "downfall_outperform_count": 4, "downfall_win_rate": 0.66,
        "index_upward_months_len": 6, "start_upward_months_len": 6,
        "index_upward_avg_return": 0.04, "start_upward_avg_return": 0.05,
        "upward_excess_avg_return": 0.01, "upward_outperform_count": 3, "upward_win_rate": 0.5,
        "index_daily_gain_days": 60, "start_daily_gain_days": 65,
        "index_daily_loss_days": 55, "start_daily_loss_days": 50,
        "index_daily_gain_loss_ratio": 1.09, "start_daily_gain_loss_ratio": 1.3,
        "index_net_value_left": 1.0, "start_net_value_left": 1.0,
        "index_net_value_right": 1.10 + tag, "start_net_value_right": 1.30,
        "index_consecutive": {"max_gain_months": 3, "max_loss_months": 2},
        "start_consecutive": {"max_gain_months": 4, "max_loss_months": 1},
        "index_new_high_avg_interval_months": 2.5, "start_new_high_avg_interval_months": 2.0,
    }


def _benchmark_runs_for_alignment(tag_a=0.0, tag_b=None):
    runs = [SimpleNamespace(code="AAA.US", weight=1, label="指数(AAA.US 100%)",
                            result=SimpleNamespace(metrics=_rich_metrics(tag_a), index_df=pd.DataFrame(
                                {"date": pd.to_datetime(["2024-01-02", "2024-01-03"])})))]
    if tag_b is not None:
        runs.append(SimpleNamespace(code="BBB.US", weight=0.3, label="指数(BBB.US 30%)",
                                    result=SimpleNamespace(metrics=_rich_metrics(tag_b), index_df=pd.DataFrame(
                                        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"])}))))
    return runs


def _all_stock_report_request():
    return type("Request", (), {
        "report_type": "RPT-M",
        "title": "多基准报告",
        "metadata": {},
        "products": [
            {"stock_code": "AAA.US", "product_name": "A", "ratio": "50"},
            {"stock_code": "BBB.US", "product_name": "B", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [_entry("AAA.US"), _entry("BBB.US")],
    })()


def test_build_report_data_places_correlation_after_weight_tables(monkeypatch):
    """相关系数热力图紧跟策略/指数权重表之后，位于分析图表区之前。"""
    service = StrategyBacktestReportService()
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: _StubKlineService())
    # 资产值全部缺失（视为个股）时列头为 净资产。
    monkeypatch.setattr(report_module, "get_etf_total_assets_detail", lambda *args, **kwargs: (None, None))
    correlation_image = {
        "type": "image", "title": "权重日涨跌幅相关系数", "path": "heatmap.png", "caption": "c",
    }

    report_data = service._build_report_data(
        _all_stock_report_request(), _benchmark_runs_for_alignment(0.0, 0.02), correlation_image,
    )

    blocks = report_data["blocks"]
    assert [(block["type"], block.get("title")) for block in blocks[:4]] == [
        ("metadata", None),
        ("table", "策略权重"),
        ("table", "指数权重"),
        ("image", "权重日涨跌幅相关系数"),
    ]
    # 后续仍是各分析章节表格，热力图不得出现在图表区末尾。
    assert blocks[4]["type"] == "heading"
    assert all(not (block["type"] == "image" and block.get("title") == "权重日涨跌幅相关系数")
               for block in blocks[4:])


def test_build_report_data_keeps_etf_header_when_any_etf_present(monkeypatch):
    """任一标的取到 ETF 资产值（totalAssets 命中）时，列头保持 ETF资产总数。"""
    service = StrategyBacktestReportService()
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: _StubKlineService())
    monkeypatch.setattr(
        report_module, "get_etf_total_assets_detail", lambda *args, **kwargs: (123.0, True),
    )

    report_data = service._build_report_data(
        _all_stock_report_request(), _benchmark_runs_for_alignment(0.0, 0.02),
    )

    weight_blocks = [block for block in report_data["blocks"] if block["type"] == "table"][:2]
    assert all(block["columns"][3] == "平均成交额 (半年)" for block in weight_blocks)
    assert all(block["columns"][4] == "ETF资产总数" for block in weight_blocks)


def test_build_report_data_tables_keep_row_column_alignment(monkeypatch):
    """N=1/N=2 全部 table 区块 rows 与 columns 列数一致（生产模板校验器口径）。

    回归：三、风险调整收益章节的超额夏普/索提诺行在 N=2 时缺指数列占位，
    触发 word_export_template 的"rows 必须与 columns 列数一致" 500。
    """
    from app.services.word_export_template import _validate_document_data

    service = StrategyBacktestReportService()
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: _StubKlineService())
    # ETF 资产总数为外网络取数，列对齐测试统一桩掉（列宽覆盖不受影响）。
    monkeypatch.setattr(report_module, "get_etf_total_assets_detail", lambda *args, **kwargs: (None, None))
    request = type("Request", (), {
        "report_type": "RPT-M",
        "title": "多基准报告",
        "metadata": {},
        "products": [
            {"stock_code": "AAA.US", "product_name": "A", "ratio": "50"},
            {"stock_code": "BBB.US", "product_name": "B", "ratio": "50"},
        ],
        "weight_allocation": None,
        "index_benchmarks": [_entry("AAA.US"), _entry("BBB.US")],
    })()

    for runs in (_benchmark_runs_for_alignment(), _benchmark_runs_for_alignment(0.0, 0.02)):
        report_data = service._build_report_data(request, runs)

        tables = [(index, block) for index, block in enumerate(report_data["blocks"], start=1)
                  if block["type"] == "table"]
        assert len(tables) >= 14
        for index, block in tables:
            assert all(len(row) == len(block["columns"]) for row in block["rows"]), \
                f"第 {index} 个 table 区块列数不一致: {block.get('title')}"
        # 直接走生产模板的数据校验器，任何区块结构问题都在测试期暴露。
        _validate_document_data(report_data)


def test_conclusion_expands_per_benchmark_for_multiple_runs():
    runs = [
        SimpleNamespace(code="AAA.US", label="指数(AAA.US)", result=SimpleNamespace(metrics={
            "index_cumulative_return": 0.10, "start_cumulative_return": 0.30,
            "excess_cumulative_return": 0.20})),
        SimpleNamespace(code="BBB.US", label="指数(BBB.US)", result=SimpleNamespace(metrics={
            "index_cumulative_return": 0.05, "start_cumulative_return": 0.30,
            "excess_cumulative_return": 0.25})),
    ]

    paragraphs = StrategyBacktestReportService()._conclusion(runs, "2024-01-01", "2024-12-31")

    assert paragraphs[0] == (
        "本报告覆盖 2024-01-01 至 2024-12-31，策略累计回报率为 30.00%，"
        "基准指数为 指数(AAA.US)、指数(BBB.US)。"
    )
    assert paragraphs[1] == "指数(AAA.US)累计回报率为 10.00%，策略相对其的累计超额回报为 20.00%。"
    assert paragraphs[2] == "指数(BBB.US)累计回报率为 5.00%，策略相对其的累计超额回报为 25.00%。"


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


def _correlation_request(products, index_benchmarks=None, report_type="RPT-M"):
    return type("Request", (), {
        "products": products,
        "index_benchmarks": index_benchmarks,
        "report_type": report_type,
    })()


def test_correlation_matrix_computes_lower_triangle_and_mirrors(monkeypatch):
    daily_a = [0.01, 0.02, -0.015, 0.005]
    daily_b = [0.005, -0.01, 0.03, -0.002]
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", daily_a),
        _cumulative_product("0700.HK", "腾讯控股", "50", daily_b, market_type="hk"),
    ], index_benchmarks=[_entry("0700.HK")])
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


def test_weight_metric_texts_single_fetch_covers_amount(monkeypatch):
    """单次 K 线取数产出平均成交额；同标的策略/指数行共享，窗口为截止日前半年。"""
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", [0.01, 0.02, -0.015, 0.005]),
        _cumulative_product("0700.HK", "腾讯控股", "50", [0.005, -0.01, 0.03, -0.002], market_type="hk"),
    ], index_benchmarks=[_entry("0700.HK", 30)])
    stub = _StubKlineService(rows=[
        {"volume": 1_000_000, "amount": 500_000_000},
        {"volume": 3_000_000, "amount": 1_500_000_000},
    ])
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: stub)

    amounts = StrategyBacktestReportService()._weight_metric_texts(request, "2024-01-04")

    assert amounts == {
        "600519.SS": "10.00亿",
        "0700.HK": "10.00亿",
        "0700.HK (指数)": "10.00亿",
    }
    # 每个标的只取数一次：策略行与指数行共享同一份 K 线结果；
    # start_date = 截止日 2024-01-04 往前推 182 天。
    assert [call["stock_code"] for call in stub.calls] == ["600519.SS", "0700.HK"]
    assert [(call["market_type"], call["start_date"], call["end_date"]) for call in stub.calls] == [
        ("cn", "2023-07-06", "2024-01-04"),
        ("hk", "2023-07-06", "2024-01-04"),
    ]


def test_weight_metric_texts_falls_back_to_volume_times_close(monkeypatch):
    """K 线行缺成交额（如 Yahoo 源）时按 成交量×收盘价 逐行估算。"""
    request = _correlation_request([
        _cumulative_product("TLT.US", "TLT", "100", [0.01, 0.02, -0.015, 0.005]),
    ])
    stub = _StubKlineService(rows=[
        {"volume": 1_000_000, "close": 90.0},
        {"volume": 3_000_000, "close": 100.0},
        {"volume": 2_000_000, "close": None},
    ])
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: stub)

    amounts = StrategyBacktestReportService()._weight_metric_texts(request, "2024-01-04")

    # 仅取成交量与收盘价都齐全的行：(1_000_000×90 + 3_000_000×100)/2 = 1.95亿。
    assert amounts == {"TLT.US": "1.95亿"}


def test_weight_metric_texts_degrades_to_dash_when_kline_fails(monkeypatch):
    request = _correlation_request([
        _cumulative_product("600519.SS", "贵州茅台", "50", [0.01, 0.02, -0.015, 0.005]),
    ])
    stub = _StubKlineService(error=RuntimeError("kline unavailable"))
    monkeypatch.setattr(report_module, "_report_kline_service", lambda: stub)

    amounts = StrategyBacktestReportService()._weight_metric_texts(request, "2024-01-04")

    assert amounts == {"600519.SS": "-"}

