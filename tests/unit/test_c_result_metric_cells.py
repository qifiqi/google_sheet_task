"""C 系结果单元格 → 参数配置指标提取的单元测试。"""

import pytest

from app.services.c_result_metric_cells import extract_parameter_metrics


def test_extract_c5_metrics_from_layout_cells():
    payload = {"sheet__C5 model": {
        "D2": "10.00%",
        "D10": "14.00%",
        "D15": "4",
        "D16": "2.5",
        "D17": "7.00%",
        "D18": "3",
        "D19": "1.5",
    }}

    metrics = extract_parameter_metrics(payload, {"title": "C5 model"})

    assert metrics == pytest.approx({
        "turnover_rate": 0.14,
        "max_theoretical_leverage": 4.0,
        "avg_theoretical_leverage": 2.5,
        "unit_theoretical_leverage_return": 0.07,
        "max_actual_leverage": 3.0,
        "avg_actual_leverage": 1.5,
    })


def test_extract_c7_0_2_metrics_shifts_cells_before_read():
    """C7.0.2 结果区整体 +6 行：先经统一归一平移，再按 C5 键读取。"""
    payload = {"sheet__C7 model": {
        "D16": "14.00%",
        "D21": "4",
        "D22": "250.00%",
        "D23": "7.00%",
        "D24": "150.00%",
        "D25": "75.00%",
    }}

    metrics = extract_parameter_metrics(payload, {"title": "C7.0.2 model"})

    assert metrics == pytest.approx({
        "turnover_rate": 0.14,
        "max_theoretical_leverage": 4.0,
        "avg_theoretical_leverage": 2.5,
        "unit_theoretical_leverage_return": 0.07,
        "max_actual_leverage": 1.5,
        "avg_actual_leverage": 0.75,
    })


def test_extract_c7_0_3_metrics_uses_c5_layout_without_shift():
    payload = {"sheet__C7 model": {
        "D10": "9.00%",
        "D15": "3",
        "D16": "2",
        "D17": "5.00%",
        "D18": "2",
        "D19": "1",
    }}

    metrics = extract_parameter_metrics(
        payload, {"title": "C7.0.3 model", "model_version": "c7_0_3"},
    )

    assert metrics == pytest.approx({
        "turnover_rate": 0.09,
        "max_theoretical_leverage": 3.0,
        "avg_theoretical_leverage": 2.0,
        "unit_theoretical_leverage_return": 0.05,
        "max_actual_leverage": 2.0,
        "avg_actual_leverage": 1.0,
    })


def test_extract_c3_metrics_only_has_turnover_rate():
    payload = {"sheet__C3 model": {"I15": "10.00%", "I23": "0.14"}}

    metrics = extract_parameter_metrics(payload, {"title": "C3 model"})

    assert metrics == pytest.approx({"turnover_rate": 0.14})


def test_extract_metrics_returns_empty_for_invalid_payload():
    assert extract_parameter_metrics(None, {"title": "C5"}) == {}
    assert extract_parameter_metrics({}, {"title": "C5"}) == {}
    assert extract_parameter_metrics({"sheet": "not-a-dict"}, {"title": "C5"}) == {}
