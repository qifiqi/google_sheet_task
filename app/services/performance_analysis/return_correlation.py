"""组合内日涨跌幅相关系数的统一计算。

输入与 portfolio_combiner 相同的累计收益行（``date``、
``index_return``、``start_return``）；日涨跌幅还原口径与
combine_product_returns 一致（共同交易日轴、首日从净值 1.0 还原），
供回测 Word 报告等展示端复用，避免相关口径散落到各处。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from app.services.performance_analysis.portfolio_combiner import _valid_rows, cumulative_to_daily


def aligned_daily_returns(rows: Iterable[dict[str, Any]], dates: list[str] | None = None) -> list[float] | None:
    """把累计收益行对齐到交易日轴并还原日涨跌幅序列。

    dates 缺省时使用行内全部日期升序；任一日期缺失、行非法或样本
    不足 3 天时返回 None。首日收益从净值 1.0 还原，与组合口径一致。
    """
    row_map = _valid_rows(rows)
    if not row_map:
        return None
    ordered = sorted(row_map) if dates is None else list(dates)
    if len(ordered) < 3 or any(date not in row_map for date in ordered):
        return None
    try:
        daily = cumulative_to_daily([{"date": date, **row_map[date]} for date in ordered])
    except ValueError:
        # 累计收益 ≤ -100% 导致净值归零，无法还原日涨跌幅。
        return None
    return [float(row["start_return"]) for row in daily]


def pearson_coefficient(left: list[float], right: list[float]) -> float | None:
    """两序列的 Pearson 相关系数；样本不足或零方差时返回 None。"""
    count = min(len(left), len(right))
    if count < 2:
        return None
    left = left[:count]
    right = right[:count]
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    cov = sum((x - mean_left) * (y - mean_right) for x, y in zip(left, right))
    var_left = sum((x - mean_left) ** 2 for x in left)
    var_right = sum((y - mean_right) ** 2 for y in right)
    if var_left <= 0 or var_right <= 0:
        return None
    return cov / math.sqrt(var_left * var_right)


def pairwise_correlation_matrix(daily_series: list[list[float]]) -> list[list[float | None]]:
    """已对齐日涨跌幅序列的两两 Pearson 矩阵（下三角计算、上三角镜像）。

    不可计算的格子（零方差/样本不足）为 None，对角线恒为 1。
    """
    count = len(daily_series)
    matrix: list[list[float | None]] = [[None] * count for _ in range(count)]
    for row in range(count):
        matrix[row][row] = 1.0
        for column in range(row):
            value = pearson_coefficient(daily_series[column], daily_series[row])
            matrix[row][column] = value
            matrix[column][row] = value
    return matrix
