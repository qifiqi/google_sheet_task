from datetime import datetime
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.dto.strategy_backtest_report import StrategyBacktestReportRequestDTO
from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.utils.return_series import build_return_series_fields


report_charts = ModuleType("app.services.strategy_backtest_report_charts")
report_charts.generate_report_charts = lambda *_args, **_kwargs: {}
sys.modules.setdefault("app.services.strategy_backtest_report_charts", report_charts)

from app.services.strategy_backtest_report_service import strategy_backtest_report_service


def _report_payload(**overrides):
    payload = {
        "returns": [
            {"date": "2026-08-20", "index_return": 0.01, "start_return": 0.02},
            {"date": "2026-08-21", "index_return": 0.02, "start_return": 0.03},
        ],
        "products": [{"stock_code": "600519", "product_name": "贵州茅台", "weight": "100.00%"}],
    }
    payload.update(overrides)
    return payload


class _Column(list):
    def tolist(self):
        return list(self)


class _Frame(dict):
    def __len__(self):
        return len(next(iter(self.values())))


def _report_analysis_result():
    index_df = _Frame({
        "date": _Column([datetime(2026, 8, 20), datetime(2026, 8, 21)]),
        "index_return": _Column([0.01, -0.01]),
    })
    start_df = _Frame({
        "date": _Column([datetime(2026, 8, 20), datetime(2026, 8, 21)]),
        "start_return": _Column([0.02, -0.01]),
    })
    return SimpleNamespace(metrics={}, index_df=index_df, start_df=start_df)


def test_backtest_word_report_defaults_single_product_to_rpt_s():
    request = StrategyBacktestReportRequestDTO.from_payload(_report_payload())

    assert request.report_type == "RPT-S"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"report_type": "RPT-S", "returns": []}, "请求 必须且只能指定 returns、task_id 或 Google Sheet 来源之一"),
        ({"report_type": "RPT-M", "products": [{"stock_code": "600519"}]}, "RPT-M 报告必须传入至少 2 个产品"),
    ],
)
def test_backtest_word_report_validates_source_and_product_count(payload, message):
    with pytest.raises(ValueError, match=message):
        StrategyBacktestReportRequestDTO.from_payload(_report_payload(**payload))


@pytest.mark.parametrize(
    ("report_type", "products", "expected_report_id"),
    [
        ("RPT-S", [{"stock_code": "600519"}], "RPT-S-20260821"),
        (
            "RPT-M",
            [
                {"stock_code": "600519", "weight": "50%", "returns": _report_payload()["returns"]},
                {"stock_code": "000858", "weight": "50%", "returns": _report_payload()["returns"]},
            ],
            "RPT-M-20260821",
        ),
    ],
)
def test_backtest_word_report_id_uses_report_type(
    monkeypatch,
    report_type,
    products,
    expected_report_id,
):
    class FrozenDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 8, 21, 9, 30)

    monkeypatch.setattr(
        "app.services.strategy_backtest_report_service.datetime",
        FrozenDateTime,
    )
    payload = _report_payload(
        report_type=report_type,
        products=products,
    )
    if report_type == "RPT-M":
        payload.pop("returns")
    request = StrategyBacktestReportRequestDTO.from_payload(payload)

    report_data = strategy_backtest_report_service._build_report_data(
        request,
        _report_analysis_result(),
    )

    assert report_data["blocks"][0]["items"][0]["value"] == expected_report_id


def test_v2_json_returns_are_normalized_without_a_product():
    request = StrategyBacktestReportRequestDTO.from_payload({
        "returns": _report_payload()["returns"],
    })

    assert request.report_type == "RPT-S"
    assert strategy_backtest_report_service._resolve_returns(request) == _report_payload()["returns"]


def test_v2_google_sheet_returns_are_normalized(monkeypatch):
    monkeypatch.setattr(
        "app.services.strategy_backtest_report_service.xpl_analyzer.get_google_sheet_data",
        lambda spreadsheet_id, sheet_name: (
            _report_payload()["returns"],
            {},
            None,
        ) if (spreadsheet_id, sheet_name) == ("sheet-id", "回测") else None,
    )
    request = StrategyBacktestReportRequestDTO.from_payload({
        "google_sheet_url": "https://docs.google.com/spreadsheets/d/sheet-id/edit",
        "google_sheet_name": "回测",
    })

    assert strategy_backtest_report_service._resolve_returns(request) == _report_payload()["returns"]


def test_single_product_task_uses_linked_return_series(app_factory):
    with app_factory.app_context():
        task = Task(id="word-report-task", name="单品", task_type="backtest_training", status="completed", config="{}")
        series = TaskResultReturn(
            task_id=task.id,
            **build_return_series_fields(
                _report_payload()["returns"],
                stock_code="600519",
                stock_name="贵州茅台",
            ),
        )
        db.session.add_all([task, series])
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result="{}",
            return_series_id=series.id,
            success=True,
        ))
        db.session.commit()

        request = StrategyBacktestReportRequestDTO.from_payload({"task_id": task.id})

        assert strategy_backtest_report_service._resolve_returns(request) == _report_payload()["returns"]


def test_multi_product_returns_are_weighted_as_daily_returns():
    request = StrategyBacktestReportRequestDTO.from_payload({
        "report_type": "RPT-M",
        "products": [
            {
                "weight": "50%",
                "returns": [
                    {"date": "2026-08-20", "index_return": 0.05, "start_return": 0.10},
                    {"date": "2026-08-21", "index_return": 0.1025, "start_return": 0.21},
                ],
            },
            {
                "weight": "50%",
                "returns": [
                    {"date": "2026-08-20", "index_return": 0.10, "start_return": 0.20},
                    {"date": "2026-08-21", "index_return": 0.10, "start_return": 0.20},
                ],
            },
        ],
    })

    returns = strategy_backtest_report_service._resolve_returns(request)

    assert returns[0]["index_return"] == pytest.approx(0.075)
    assert returns[0]["start_return"] == pytest.approx(0.15)
    assert returns[1]["index_return"] == pytest.approx(0.101875)
    assert returns[1]["start_return"] == pytest.approx(0.2075)


def test_word_report_uses_full_template_sections_and_cumulative_nav():
    result = SimpleNamespace(
        metrics={
            "index_cumulative_return": -0.01,
            "start_cumulative_return": -0.01,
            "excess_cumulative_return": 0.0,
            "index_monthly_return_skewness": 0.12,
            "start_monthly_return_skewness": 0.34,
            "index_monthly_return_kurtosis": 0.56,
            "start_monthly_return_kurtosis": 0.78,
            "index_mean_daily_skewness": 0.21,
            "start_mean_daily_skewness": 0.43,
            "index_mean_daily_kurtosis": 0.65,
            "start_mean_daily_kurtosis": 0.87,
        },
        index_df=_Frame({
            "date": _Column([datetime(2026, 8, 20), datetime(2026, 8, 21)]),
            "index_return": _Column([0.01, -0.01]),
        }),
        start_df=_Frame({
            "date": _Column([datetime(2026, 8, 20), datetime(2026, 8, 21)]),
            "start_return": _Column([0.02, -0.01]),
        }),
        excess_df=_Frame({
            "date": _Column([datetime(2026, 8, 20), datetime(2026, 8, 21)]),
            "excess_return": _Column([0.01, 0.0]),
        }),
    )

    sections = strategy_backtest_report_service._sections(result.metrics, result)
    chart_data = strategy_backtest_report_service._build_chart_data(result)

    assert [section["title"] for section in sections] == [
        "一、收益类指标",
        "二、风险类指标",
        "三、风险调整收益指标",
        "四、月度收益分布",
        "五、日度收益分布",
        "六、超额收益分析",
        "七、极端行情表现",
        "八、资金曲线特征",
    ]
    assert [len(section["subsections"]) for section in sections] == [3, 2, 1, 2, 3, 3, 3, 1]
    assert sections[0]["subsections"][0]["table"]["rows"][0] == [
        "累计回报率", "-1.00%", "-1.00%", "0.00%",
    ]
    monthly_summary_rows = sections[3]["subsections"][0]["table"]["rows"]
    daily_summary_rows = sections[4]["subsections"][0]["table"]["rows"]
    assert monthly_summary_rows[-2:] == [
        ["月收益率偏度", "0.1200", "0.3400"],
        ["月收益率峰度", "0.5600", "0.7800"],
    ]
    assert daily_summary_rows[-2:] == [
        ["日收益率偏度", "0.2100", "0.4300"],
        ["日收益率峰度", "0.6500", "0.8700"],
    ]
    assert sections[3]["subsections"][1]["table"]["columns"] == [
        "收益区间", "指数月数", "指数占比", "策略月数", "策略占比",
    ]
    assert sections[4]["subsections"][2]["table"]["columns"] == [
        "收益区间", "指数天数", "指数占比", "策略天数", "策略占比",
    ]
    assert sections[2]["subsections"][0]["table"]["columns"] == ["指标", "指数", "策略"]
    excess_distribution = sections[5]["subsections"][1]["table"]
    assert excess_distribution["columns"] == ["超额区间", "月数", "占比"]
    assert all(len(row) == 3 for row in excess_distribution["rows"])
    assert chart_data["index_nav"] == [1.01, 0.99]
    assert chart_data["strategy_nav"] == [1.02, 0.99]
    assert chart_data["excess_nav"] == [1.01, 1.0]


def test_xpl_v2_page_exposes_all_data_sources(app_factory):
    response = app_factory.test_client().get('/xpl/v2')

    assert response.status_code == 200
    assert 'V2：回测数据分析' in response.get_data(as_text=True)
    assert 'Google Sheet' in response.get_data(as_text=True)
    assert '粘贴数据' in response.get_data(as_text=True)
    assert '导入 Excel' in response.get_data(as_text=True)
    assert 'id="btn-analyze-v2"' in response.get_data(as_text=True)
    assert 'id="btn-export-word"' in response.get_data(as_text=True)
    assert 'id="word-export-options-modal"' in response.get_data(as_text=True)
    assert '/api/search-stocks?q=${encodeURIComponent(keyword)}&page_size=10' in response.get_data(as_text=True)
    assert "ratio: '100.00%'" in response.get_data(as_text=True)
    assert 'date / index_return / start_return' in response.get_data(as_text=True)
    assert 'xlsx-js-style' in response.get_data(as_text=True)
    assert 'function applyV2ExportStyles' in response.get_data(as_text=True)
    assert 'XLSX.writeFile(workbook, defaultFilename' in response.get_data(as_text=True)


def test_xpl_v2_accepts_portfolio_return_rows(app_factory):
    response = app_factory.test_client().post('/xpl/analyze', json={
        "data": "\n".join([
            "2024-01-01\t0.01\t0.02",
            "2024-01-02\t0.02\t0.03",
            "2024-01-03\t0.01\t0.01",
        ]),
        "time_format": "auto",
    })

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
