"""return_correlation 相关系数统一计算的单元测试。"""

import pytest

from app.services.performance_analysis.return_correlation import (
    aligned_daily_returns,
    pairwise_correlation_matrix,
    pearson_coefficient,
)


def _rows(daily):
    """日涨跌幅转累计收益行（date/index_return/start_return），与真实载荷同构。"""
    cumulative = []
    current = 0.0
    for value in daily:
        current = (1 + value) * (1 + current) - 1
        cumulative.append(current)
    return [
        {
            "date": f"2024-01-{offset + 1:02d}",
            "index_return": 0.0,
            "start_return": value,
        }
        for offset, value in enumerate(cumulative)
    ]


def test_aligned_daily_returns_restores_full_series_on_given_axis():
    daily = [0.01, -0.02, 0.03, 0.015]
    dates = [f"2024-01-{offset + 1:02d}" for offset in range(4)]

    assert aligned_daily_returns(_rows(daily), dates) == pytest.approx(daily)


def test_aligned_daily_returns_requires_every_axis_date():
    rows = _rows([0.01, 0.02, -0.01])
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]

    assert aligned_daily_returns(rows, dates) is None
    # 缺省轴时使用行内全部日期，仍可还原。
    assert aligned_daily_returns(rows) == pytest.approx([0.01, 0.02, -0.01])


def test_aligned_daily_returns_rejects_degenerate_inputs():
    assert aligned_daily_returns([]) is None
    assert aligned_daily_returns(_rows([0.01, 0.02])) is None
    # 累计收益跌到 -100% 后净值归零，无法还原日涨跌幅。
    assert aligned_daily_returns([
        {"date": "2024-01-01", "index_return": 0.0, "start_return": 0.1},
        {"date": "2024-01-02", "index_return": 0.0, "start_return": -1.0},
        {"date": "2024-01-03", "index_return": 0.0, "start_return": 0.2},
    ]) is None


def test_pearson_coefficient_flags_zero_variance_and_short_samples():
    assert pearson_coefficient([0.01, 0.02, 0.03], [0.01, 0.02, 0.03]) == pytest.approx(1.0)
    assert pearson_coefficient([0.01, 0.02, 0.03], [-0.03, -0.02, -0.01]) == pytest.approx(1.0)
    assert pearson_coefficient([0.01, 0.02, 0.03], [0.02, 0.02, 0.02]) is None
    assert pearson_coefficient([0.01], [0.02]) is None


def test_pairwise_correlation_matrix_is_symmetric_with_none_for_degenerate_pairs():
    left = [0.01, 0.02, -0.01]
    right = [0.03, -0.01, 0.02]
    constant = [0.01, 0.01, 0.01]

    matrix = pairwise_correlation_matrix([left, right, constant])

    assert matrix[0][0] == 1.0
    assert matrix[1][1] == 1.0
    assert matrix[2][2] == 1.0
    assert matrix[0][1] == pytest.approx(matrix[1][0])
    assert matrix[0][1] == pytest.approx(pearson_coefficient(left, right))
    # 常数序列方差为 0，与其余产品的相关系数不可计算。
    assert matrix[0][2] is None and matrix[2][0] is None
    assert matrix[1][2] is None and matrix[2][1] is None


def test_pairwise_correlation_matrix_handles_empty_and_single_series():
    assert pairwise_correlation_matrix([]) == []
    single = pairwise_correlation_matrix([[0.01, 0.02, 0.03]])
    assert single == [[1.0]]
