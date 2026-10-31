"""统一导出文件名规范单测：build_export_filename 与区间/模型版本提取。

规范：{基名}-{模型版本}-{价格/复权}-{K线起}-{K线止}-{导出时间}.{扩展名}
段间 `-`、段内 `_`；模型版本/价格复权/区间缺失整段省略，导出时间恒在。
"""

import json
import zipfile
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

from app.services.export_workbook_service import (
    build_c7_stock_code_export_archive,
    build_export_filename,
    build_task_export,
    compose_preview_stem,
    kline_bounds_from_params,
    kline_bounds_from_results,
    model_version_from_config,
    model_version_from_results,
    price_adjust_filename_segment,
)


def _c11_task(config_overrides=None):
    config = {
        "sheets": [{"spreadsheet_id": "s", "sheet_name": "control", "title": "C1.1.0", "model_version": "c1_1"}],
        "price_mode": "random_price",
        "random_price_range": "high_low",
        "parameters": [["SOXX"]],
        "token_type": "file",
        "token_file": "x",
        "token_id": 1,
    }
    config.update(config_overrides or {})
    # 导出链路拿到的是 ORM 实体：config 为 JSON 文本，不是 dict
    return SimpleNamespace(id="t1", name="c1.1.0-三只股票", task_type="google_sheet_C1_1",
                           config=json.dumps(config))


def _c11_result(stock_code="SOXX"):
    return {"parameters": {"stock_code": stock_code, "kline_key": "2026"}, "result": {}, "success": True, "step_index": 0}

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


def test_price_adjust_filename_segment_real_and_random():
    # 真实行情：价格-复权拼接；缺一段只带另一段
    assert price_adjust_filename_segment(
        {"price_mode": "sp_price", "kline_adjustment": "forward"}
    ) == "close-qfq"
    assert price_adjust_filename_segment(
        {"price_mode": "kp_price", "kline_adjustment": "back"}
    ) == "open-hfq"
    assert price_adjust_filename_segment(
        {"price_mode": "ohlc_price", "kline_adjustment": "none"}
    ) == "ohlc-raw"
    assert price_adjust_filename_segment({"price_mode": "sp_price"}) == "close"
    # 随机价：带区间子标记，复权无语义不拼接；区间未知回落 rnd
    assert price_adjust_filename_segment(
        {"price_mode": "random_price", "random_price_range": "high_low", "kline_adjustment": "forward"}
    ) == "rnd-hl"
    assert price_adjust_filename_segment(
        {"price_mode": "random_price", "random_price_range": "open_close"}
    ) == "rnd-oc"
    assert price_adjust_filename_segment({"price_mode": "random_price"}) == "rnd"
    # 未知/缺失/非 dict 配置整段省略
    assert price_adjust_filename_segment({"price_mode": "unknown"}) == ""
    assert price_adjust_filename_segment({}) == ""
    assert price_adjust_filename_segment(None) == ""
    assert price_adjust_filename_segment("历史JSON串") == ""


def test_build_export_filename_with_price_adjust_segment():
    filename = build_export_filename(
        "贵州茅台", "c1_1", "2023-01-01", "2023-12-29",
        price_adjust="close-qfq", now=FROZEN_NOW,
    )
    assert filename == "贵州茅台-C1.1.0-close-qfq-20230101-20231229-20261023_153000.xlsx"
    # 段缺失整段省略（存量命名不受影响）
    assert build_export_filename("任务A", "", "", "", now=FROZEN_NOW) == \
        "任务A-20261023_153000.xlsx"


def test_compose_preview_stem_with_price_adjust():
    stem = compose_preview_stem("c1_1", "600519", "2023-01-01", "2023-12-29", price_adjust="rnd-oc")
    assert stem == "C1.1.0-rnd-oc-600519_20230101-20231229"
    assert compose_preview_stem("c1_1", "600519", "2023-01-01", "2023-12-29") == \
        "C1.1.0-600519_20230101-20231229"


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


def test_single_task_export_reads_entity_config_for_price_segment():
    """ORM 实体的 config 是 JSON 文本：单任务 Excel 也要带 rnd-hl 段。"""
    export = build_task_export(_c11_task(), [_c11_result()])
    assert "-rnd-hl-" in export.filename, export.filename


def test_stock_zip_outer_and_members_carry_price_segment():
    """按股票 zip：外层与成员名都要带价格段（与全局预览出口同口径）。"""
    archive = build_c7_stock_code_export_archive(_c11_task(), [_c11_result()])
    assert "-rnd-hl-" in archive.filename, archive.filename
    with zipfile.ZipFile(BytesIO(archive.buffer.getvalue())) as bundle:
        members = bundle.namelist()
    assert members and all("rnd-hl" in name for name in members), members
