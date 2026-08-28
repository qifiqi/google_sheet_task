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

report_template = ModuleType("app.services.strategy_backtest_report_template")
report_template.generate_strategy_backtest_report = lambda *_args, **_kwargs: None
sys.modules.setdefault("app.services.strategy_backtest_report_template", report_template)

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
        metadata={"report_id": "CLIENT-SUPPLIED"},
    )
    if report_type == "RPT-M":
        payload.pop("returns")
    request = StrategyBacktestReportRequestDTO.from_payload(payload)

    report_data = strategy_backtest_report_service._build_report_data(
        request,
        _report_analysis_result(),
    )

    assert report_data["metadata"]["report_id"] == expected_report_id


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
        metrics={},
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
    assert 'date / index_return / start_return' in response.get_data(as_text=True)
    assert 'xlsx-js-style' in response.get_data(as_text=True)
    assert 'function applyV2ExportStyles' in response.get_data(as_text=True)
    assert 'XLSX.writeFile(workbook, defaultFilename' in response.get_data(as_text=True)
