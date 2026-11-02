"""全局预览导出·每月收益率表 单元测试。

覆盖两件事：
1. payload 层 ``include_monthly_returns`` 开关：导出侧成功列附带逐月收益序列
   （metrics.monthly_excess_returns），预览 API 默认路径保持轻量不透传；
2. workbook 层：数据子 sheet 指标表下方按年分块（月份 12→1 倒序）、每个结果列
   一组「指数/模型/超额」，组头复用该列第 1 行参数头，缺月留空，无数据整块跳过。
"""

from datetime import datetime

import pytest

from app.models import Task, TaskResult
from app.services.backtest_report_query_service import (
    _build_global_preview_payload_from_results,
    _monthly_returns_grid,
    build_global_preview_workbook,
)

_SUMMARY_ROWS = (
    "2018-01-02/2026-10-29",
    [{"category": "绝对收益", "metric": "年化收益", "index_value": "29.90%", "model_value": "35.47%"}],
)

_MONTHLY_RESULT_JSON = (
    '{"SOXL.US__2026-2018": {"metrics_payload": {"metrics": {"monthly_excess_returns": ['
    '{"year_month": "2026-10", "index_monthly_return": 0.01,'
    ' "start_monthly_return": 0.05, "monthly_excess_return_diff": 0.04}],'
    ' "index_returns_rate": [{"year": "2026", "annual_return": 0.10}],'
    ' "start_returns_rate": [{"year": "2026", "annual_return": 0.30}]}}}}'
)


def _make_task(task_id="preview-monthly"):
    return Task(
        id=task_id,
        name="预览任务",
        task_type="google_sheet_c7",
        status="completed",
        config="{}",
    )


def _make_result(result_json):
    return TaskResult(
        task_id="preview-monthly",
        step_index=0,
        parameters=(
            '{"stock_code":"SOXL.US","kline_key":"2026-2018",'
            '"parameter":["","3"],"model_version":"c7_0_3"}'
        ),
        result=result_json,
        success=True,
        timestamp=datetime(2026, 10, 29, 10, 0, 0),
    )


@pytest.fixture()
def preview_service_stubs(monkeypatch):
    """屏蔽汇总行提取与收益序列仓储，聚焦月度序列透传本身。"""
    monkeypatch.setattr(
        "app.services.backtest_report_query_service._extract_summary_rows",
        lambda _metrics: _SUMMARY_ROWS,
    )
    monkeypatch.setattr(
        "app.services.backtest_report_query_service._with_excess_return_preview_row",
        lambda summary_rows, _column, _metrics: summary_rows,
    )
    monkeypatch.setattr(
        "app.repositories.task_result_repository.list_return_entities",
        lambda _ids: [],
    )


def test_payload_flag_attaches_monthly_returns_to_success_columns(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(),
        [_make_result(_MONTHLY_RESULT_JSON)],
        include_monthly_returns=True,
    )

    column = payload["groups"][0]["columns"][0]
    assert column["monthly_returns"] == [
        {
            "year_month": "2026-10",
            "index_monthly_return": 0.01,
            "start_monthly_return": 0.05,
            "monthly_excess_return_diff": 0.04,
        },
    ]
    # 年度收益复用执行期回算（index/start_returns_rate 合并），超额由消费方相减。
    assert column["year_returns"] == [
        {"year": "2026", "index_annual_return": 0.10, "start_annual_return": 0.30},
    ]


def test_payload_default_keeps_columns_without_monthly_returns(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(),
        [_make_result(_MONTHLY_RESULT_JSON)],
    )

    column = payload["groups"][0]["columns"][0]
    assert "monthly_returns" not in column
    assert "year_returns" not in column


def test_monthly_returns_grid_merges_columns_and_skips_malformed_records():
    columns = [
        {
            "column_key": "result_1",
            "monthly_returns": [
                {
                    "year_month": "2026-10",
                    "index_monthly_return": 0.01,
                    "start_monthly_return": 0.05,
                    "monthly_excess_return_diff": 0.04,
                },
                {"year_month": "bad-record", "index_monthly_return": 9},
            ],
        },
        {
            "column_key": "result_2",
            "monthly_returns": [
                {
                    "year_month": "2018-01",
                    "index_monthly_return": -0.02,
                    "start_monthly_return": 0.03,
                    "monthly_excess_return_diff": 0.05,
                },
            ],
        },
        {"column_key": "result_3"},
    ]

    grid = _monthly_returns_grid(columns)

    assert set(grid.keys()) == {"2026", "2018"}
    assert grid["2026"][10]["result_1"] == (0.01, 0.05, 0.04)
    assert grid["2018"][1]["result_2"] == (-0.02, 0.03, 0.05)


def _preview_payload_with_monthly():
    """构造带两条结果列的单品预览载荷：结果 1 只有 2026-10（含 NaN 月），
    结果 2 只有 2018-01，用于核对年块、缺月留空与非有限值过滤。"""
    return {
        "task": {
            "id": "preview-monthly",
            "name": "预览任务",
            "status": "completed",
            "stock_code": "SOXL.US",
        },
        "summary": {
            "total_results": 2,
            "success_results": 2,
            "failed_results": 0,
            "group_count": 1,
            "stock_count": 1,
        },
        "groups": [
            {
                "group_key": "SOXL.US::2026-2018",
                "group_label": "2026-2018 年",
                "stock_code": "SOXL.US",
                "year": "2026-2018",
                "period": "2018-01-02/2026-10-29",
                "columns": [
                    {
                        "column_key": "result_1",
                        "result_id": 1,
                        "step_index": 0,
                        "return_series_id": None,
                        "word_report_payload": None,
                        "header": " / 3",
                        "model_name": "C7",
                        "model_version": "c7_0_3",
                        "success": True,
                        "timestamp": None,
                        "parameter_values": ["", "3"],
                        "raw_metrics": {},
                        "monthly_returns": [
                            {
                                "year_month": "2026-10",
                                "index_monthly_return": 0.01,
                                "start_monthly_return": 0.05,
                                "monthly_excess_return_diff": 0.04,
                            },
                            {
                                "year_month": "2026-11",
                                "index_monthly_return": float("nan"),
                                "start_monthly_return": float("nan"),
                                "monthly_excess_return_diff": float("nan"),
                            },
                        ],
                        "year_returns": [
                            {"year": "2026", "index_annual_return": 0.10, "start_annual_return": 0.30},
                        ],
                    },
                    {
                        "column_key": "result_2",
                        "result_id": 2,
                        "step_index": 1,
                        "return_series_id": None,
                        "word_report_payload": None,
                        "header": "N/M",
                        "model_name": "C7",
                        "model_version": None,
                        "success": True,
                        "timestamp": None,
                        "parameter_values": ["N", "M"],
                        "raw_metrics": {},
                        "monthly_returns": [
                            {
                                "year_month": "2018-01",
                                "index_monthly_return": -0.02,
                                "start_monthly_return": 0.03,
                                "monthly_excess_return_diff": 0.05,
                            },
                        ],
                        "year_returns": [
                            {"year": "2018", "index_annual_return": -0.05, "start_annual_return": 0.06},
                        ],
                    },
                ],
                "rows": [
                    {
                        "category": "绝对收益",
                        "metric": "年化收益",
                        "index_value": "29.90%",
                        "values": {"result_1": "35.47%", "result_2": "40.00%"},
                    },
                ],
                "failed_results": 0,
                "column_count": 2,
            },
        ],
    }


def test_workbook_appends_monthly_returns_block_below_summary():
    payload = _preview_payload_with_monthly()

    sheet = build_global_preview_workbook(payload)["2026-2018 年"]

    # 指标区占第 1-3 行，空两行后第 6 行起为月度收益率表：年份行身兼列名行
    # （A 列年份 + 各组「指数/模型/超额」平铺，无合并单元格），每块 14 行
    # （列名行 + 全年行 + 12 行月份）。
    assert sheet["A6"].value == 2026
    assert [sheet.cell(row=6, column=c).value for c in range(2, 8)] == [
        "指数", "模型", "超额", "指数", "模型", "超额",
    ]

    # 2026 年块：第 7 行为全年汇总（复用年度回算，超额 = 模型 − 指数），
    # 第 8-19 行月份 12→1 倒序；10 月有值且为百分比格式，11 月 NaN 留空。
    assert sheet["A7"].value == "全年"
    assert sheet["B7"].value == 0.10
    assert sheet["C7"].value == 0.30
    assert sheet["D7"].value == pytest.approx(0.20)
    assert sheet["B7"].number_format == "0.00%"
    assert sheet["E7"].value is None
    assert [sheet.cell(row=r, column=1).value for r in range(8, 20)] == list(range(12, 0, -1))
    assert sheet["B10"].value == 0.01
    assert sheet["C10"].value == 0.05
    assert sheet["D10"].value == 0.04
    assert sheet["B10"].number_format == "0.00%"
    assert sheet["B8"].value is None
    assert sheet["B9"].value is None

    # 2018 年块：第 20 行起（列名行同样平铺），全年行第 21 行落在结果 2 组列，
    # 仅 1 月（第 33 行）有值。
    assert sheet["A20"].value == 2018
    assert sheet["B20"].value == "指数"
    assert sheet["E20"].value == "指数"
    assert sheet["A21"].value == "全年"
    assert sheet["B21"].value is None
    assert sheet["E21"].value == -0.05
    assert sheet["F21"].value == 0.06
    assert sheet["G21"].value == pytest.approx(0.11)
    assert sheet["E33"].value == -0.02
    assert sheet["F33"].value == 0.03
    assert sheet["G33"].value == 0.05
    assert sheet.max_row == 33

    # 指标区与月度表之间空两行；“区间”列仍紧贴指标区（2 列结果 → F 列）。
    assert sheet["A4"].value is None
    assert sheet["F1"].value == "区间"
    assert sheet["F2"].value == "2018-01-02/2026-10-29"

    # 年块列头行整行橙色（着色6 浅色40%），全年行加粗，月份行 A 列维持首列黄底。
    assert sheet["A6"].fill.fgColor.rgb.endswith("F4B183")
    assert sheet["G6"].fill.fgColor.rgb.endswith("F4B183")
    assert sheet["A20"].fill.fgColor.rgb.endswith("F4B183")
    assert sheet["A7"].fill.fgColor.rgb.endswith("F7E1A1")
    assert sheet["A7"].font.bold is True
    assert sheet["B7"].font.bold is True
    assert sheet["B10"].font.bold is not True


def test_workbook_skips_monthly_block_when_no_column_has_monthly_data():
    payload = _preview_payload_with_monthly()
    for column in payload["groups"][0]["columns"]:
        column.pop("monthly_returns")

    sheet = build_global_preview_workbook(payload)["2026-2018 年"]

    assert sheet.max_row == 3


def test_workbook_omits_annual_row_when_no_column_has_year_returns():
    """老结果缺年度回算键时省去全年行，回退 13 行块（列名行 + 12 行月份）。"""
    payload = _preview_payload_with_monthly()
    for column in payload["groups"][0]["columns"]:
        column.pop("year_returns")

    sheet = build_global_preview_workbook(payload)["2026-2018 年"]

    assert sheet["A6"].value == 2026
    assert sheet["A7"].value == 12
    assert sheet["A19"].value == 2018
    assert sheet["A20"].value == 12
    assert sheet.max_row == 31
