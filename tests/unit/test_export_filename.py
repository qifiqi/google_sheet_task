"""统一导出文件名规范单测：build_export_filename 与区间/模型版本提取。

规范：{基名}-{模型版本}-{K线起}-{K线止}-{导出时间}.{扩展名}
段间 `-`、段内 `_`；模型版本/区间缺失整段省略，导出时间恒在。
"""

from datetime import datetime
from types import SimpleNamespace

from app.services.export_workbook_service import (
    build_export_filename,
    kline_bounds_from_params,
    kline_bounds_from_results,
    model_version_from_config,
    model_version_from_results,
)

FROZEN_NOW = datetime(2026, 10, 23, 15, 30, 0)


def test_build_export_filename_full_segments():
    filename = build_export_filename(
        "C7多模型验证", "c7_0_3", "2023-01-01", "2023-12-29", now=FROZEN_NOW,
    )
    assert filename == "C7多模型验证-C7.0.3-20230101-20231229-20261023_153000.xlsx"


def test_build_export_filename_normalizes_date_formats():
    filename = build_export_filename(
        "任务A", "", "2024-12-31 00:00:00", "2024/1/2", now=FROZEN_NOW,
    )
    # 起止按时间升序输出
    assert filename == "任务A-20240102-20241231-20261023_153000.xlsx"


def test_build_export_filename_omits_partial_range_and_optional_extension():
    # 区间只缺一端时整段省略；extension 为空返回词干（zip 成员名复用）
    filename = build_export_filename(
        "任务A", "c5", "2024-01-02", "", now=FROZEN_NOW, extension="",
    )
    assert filename == "任务A-C5-20261023_153000"


def test_build_export_filename_truncates_long_base():
    filename = build_export_filename("超长任务名" * 60, "", "", "", now=FROZEN_NOW)
    stem = filename.rsplit(".", 1)[0]
    assert len(stem) <= 180
    assert stem.endswith("-20261023_153000")


def test_kline_bounds_envelope_across_results():
    results = [
        {"parameters": {"kline": [{"stock_date": "2023-01-01"}, {"stock_date": "2023-06-30"}]}},
        {"parameters": {"kline": [{"stock_date": "2024-01-02"}, {"stock_date": "2024-12-31"}]}},
        {"parameters": {"kline": []}},
        {"parameters": "不是字典"},
    ]
    assert kline_bounds_from_results(results) == ("2023-01-01", "2024-12-31")
    assert kline_bounds_from_results([]) == ("", "")
    assert kline_bounds_from_params({"kline": [{"stock_date": ""}]}) == ("", "")


def test_model_version_from_results_single_mixed_and_task_fallback():
    task = SimpleNamespace(id="t", name="n", task_type="google_sheet_C7")
    single = [
        {"parameters": {"model_version": "c7_0_3"}},
        {"parameters": {"model_version": "c7_0_3"}},
    ]
    assert model_version_from_results(single, task) == "c7_0_3"

    mixed = [
        {"parameters": {"model_version": "c7_0_2"}},
        {"parameters": {"model_version": "c7_0_3"}},
    ]
    # 混版本无包络表达，省略该段
    assert model_version_from_results(mixed, task) == ""

    # 无打标回落任务类型推断
    assert model_version_from_results([{"parameters": {}}], task) == "c7_0_2"


def test_model_version_from_config_prefers_sheet_then_root():
    sheets_config = {"sheets": [{"model_version": "c7_0_3"}, {"model_version": "c7_0_2"}]}
    assert model_version_from_config(sheets_config) == "c7_0_3"
    assert model_version_from_config({"model_version": "C7.0.3"}) == "c7_0_3"
    assert model_version_from_config({}) == ""
    assert model_version_from_config(None) == ""
