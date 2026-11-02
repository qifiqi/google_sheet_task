"""C1.1 全局预览导出单元测试。

覆盖 2026-10-30 两处修复：
1. 汇总 sheet 六行取数：C1.1 结果块（E 列标签/F 列值，默认 F2:F26）按行偏移
   取 F4/F6/F8/F10，超额两行相减派生；历史上 C1.1.0 不在 SUMMARY_METRIC_CELL_MAP，
   回落 C3 单元格导致汇总列全空。
2. 列头价格类型取值：C1.1 无参数组合，列标识 = 价格类型（随机价 = random-N
   随机组 key；真实价 = 收盘价等价格名，由任务配置 random_price_range 解析），
   汇总表头/月度块组头/明细首行三处同源展示该取值。
"""

from datetime import datetime

import pytest

from app.models import Task, TaskResult
from app.services.backtest_report_query_service import (
    _build_global_preview_payload_from_results,
    _build_parameter_header,
    _get_summary_derived_value,
    build_global_preview_workbook,
)

_REAL_PARAMETERS_JSON = (
    '{"stock_code":"SOXL.US","kline_key":"2026-2018",'
    '"model_version":"c1_1","c1_1_output_range":"F2:F26"}'
)
_RANDOM_PARAMETERS_JSON = (
    '{"stock_code":"SOXL.US","kline_key":"2026-2018:random-3",'
    '"model_version":"c1_1","random_group":3,"c1_1_output_range":"F2:F26"}'
)
_P_ANCHOR_PARAMETERS_JSON = (
    '{"stock_code":"SOXL.US","kline_key":"2026-2018",'
    '"model_version":"c1_1","c1_1_output_range":"P2:P26"}'
)
_F_CELL_RESULT_JSON = (
    '{"SOXL.US__C1.1.0": {'
    '"F4": "60.62%", "F6": "-33.78%", "F8": "40.45%", "F10": "-32.00%",'
    '"metrics_payload": {"metrics": {}}}}'
)
_P_CELL_RESULT_JSON = (
    '{"SOXL.US__C1.1.0": {'
    '"P4": "10.00%", "P6": "-20.00%", "P8": "4.00%", "P10": "-8.00%",'
    '"metrics_payload": {"metrics": {}}}}'
)


def _make_task(task_id="c1-1-preview", random_price_range="sp_price"):
    return Task(
        id=task_id,
        name="C1.1 预览任务",
        task_type="google_sheet_c1_1",
        status="completed",
        config=f'{{"random_price_range":"{random_price_range}"}}',
    )


def _make_result(parameters_json, result_json):
    return TaskResult(
        task_id="c1-1-preview",
        step_index=0,
        parameters=parameters_json,
        result=result_json,
        success=True,
        timestamp=datetime(2026, 10, 30, 10, 0, 0),
    )


@pytest.fixture()
def preview_service_stubs(monkeypatch):
    """屏蔽 21 项契约行提取与收益序列仓储，聚焦汇总取数与列头渲染。"""
    monkeypatch.setattr(
        "app.services.backtest_report_query_service._extract_summary_rows",
        lambda _metrics: (
            "2026-01-02/2026-10-22",
            [
                {
                    "category": "绝对收益",
                    "metric": "年化收益",
                    "index_value": "28.13%",
                    "model_value": "38.63%",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.backtest_report_query_service._with_excess_return_preview_row",
        lambda summary_rows, _column, _metrics: summary_rows,
    )
    monkeypatch.setattr(
        "app.repositories.task_result_repository.list_return_entities",
        lambda _ids: [],
    )


def test_build_parameter_header_c1_1_price_type_variants():
    assert _build_parameter_header({"model_version": "c1_1"}, "收盘价") == "收盘价"
    assert _build_parameter_header({"model_version": "c1_1"}) == "C1.1.0"
    assert _build_parameter_header({"model_version": "c1_1", "random_group": 3}) == "random-3"
    # 非 C1.1 取数路径不受影响
    assert _build_parameter_header({"A1": 7, "B1": 3}) == "7 / 3"
    assert _build_parameter_header({}) == "未命名参数"


def test_c1_1_summary_derived_value_subtracts_result_block_cells():
    column = {
        "model_name": "C1.1.0",
        "c1_1_output_range": "F2:F26",
        "raw_metrics": {"F4": "60.62%", "F6": "-33.78%", "F8": "40.45%", "F10": "-32.00%"},
    }
    assert _get_summary_derived_value(column, "return") == "60.62%"
    assert _get_summary_derived_value(column, "index_return") == "40.45%"
    assert _get_summary_derived_value(column, "excess_return") == "20.17%"
    assert _get_summary_derived_value(column, "max_drawdown") == "-33.78%"
    assert _get_summary_derived_value(column, "index_max_drawdown") == "-32.00%"
    assert _get_summary_derived_value(column, "excess_drawdown") == "-1.78%"


def test_c1_1_summary_sheet_reads_result_block_cells(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(), [_make_result(_REAL_PARAMETERS_JSON, _F_CELL_RESULT_JSON)]
    )
    column = payload["groups"][0]["columns"][0]
    assert column["header"] == "收盘价"
    assert column["c1_1_output_range"] == "F2:F26"

    sheet = build_global_preview_workbook(payload)["汇总"]
    assert sheet.cell(row=1, column=3).value == "收盘价"
    values = {
        sheet.cell(row=row, column=2).value: sheet.cell(row=row, column=3).value
        for row in range(2, 8)
    }
    assert values["指数回报"] == pytest.approx(0.4045)
    assert values["模型回报"] == pytest.approx(0.6062)
    assert values["超额回报"] == pytest.approx(0.2017)
    assert values["指数回撤"] == pytest.approx(-0.32)
    assert values["模型回撤"] == pytest.approx(-0.3378)
    assert values["超额回撤"] == pytest.approx(-0.0178)


def test_c1_1_summary_cells_follow_output_range_anchor(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(), [_make_result(_P_ANCHOR_PARAMETERS_JSON, _P_CELL_RESULT_JSON)]
    )
    sheet = build_global_preview_workbook(payload)["汇总"]
    values = {
        sheet.cell(row=row, column=2).value: sheet.cell(row=row, column=3).value
        for row in range(2, 8)
    }
    assert values["指数回报"] == pytest.approx(0.04)
    assert values["模型回报"] == pytest.approx(0.10)
    assert values["超额回报"] == pytest.approx(0.06)
    assert values["指数回撤"] == pytest.approx(-0.08)
    assert values["模型回撤"] == pytest.approx(-0.20)
    assert values["超额回撤"] == pytest.approx(-0.12)


def test_c1_1_detail_sheet_renders_price_type_value_and_model(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(), [_make_result(_REAL_PARAMETERS_JSON, _F_CELL_RESULT_JSON)]
    )
    sheet = build_global_preview_workbook(payload)["2026-2018 年"]
    assert sheet.cell(row=1, column=4).value == "收盘价"
    assert sheet.cell(row=2, column=4).value == "C1.1.0"


def test_c1_1_random_group_header_uses_random_key(preview_service_stubs):
    payload = _build_global_preview_payload_from_results(
        _make_task(random_price_range="high_low"),
        [_make_result(_RANDOM_PARAMETERS_JSON, _F_CELL_RESULT_JSON)],
    )
    column = payload["groups"][0]["columns"][0]
    assert column["header"] == "random-3"

    workbook = build_global_preview_workbook(payload)
    sheet = workbook[workbook.sheetnames[1]]
    assert sheet.cell(row=1, column=4).value == "random-3"
    assert sheet.cell(row=2, column=4).value == "C1.1.0"
