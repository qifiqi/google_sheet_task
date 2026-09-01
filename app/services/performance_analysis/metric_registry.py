"""V1 统一指标的共享展示元数据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    label: str
    group: str
    value_type: Literal["percent", "number"] = "number"
    nullable: bool = True
    preview: bool = True
    word: bool = True
    export: bool = True
    aliases: tuple[str, ...] = ()


METRIC_REGISTRY: tuple[MetricDefinition, ...] = (
    MetricDefinition("benchmark.cumulative_return", "基准累计收益", "绝对收益", "percent"),
    MetricDefinition("strategy.cumulative_return", "策略累计收益", "绝对收益", "percent"),
    MetricDefinition("benchmark.annualized_return", "基准年化收益", "绝对收益", "percent"),
    MetricDefinition("strategy.annualized_return", "策略年化收益", "绝对收益", "percent"),
    MetricDefinition("benchmark.max_drawdown", "基准最大回撤", "回撤", "percent"),
    MetricDefinition("strategy.max_drawdown", "策略最大回撤", "回撤", "percent"),
    MetricDefinition("relative.drawdown_advantage", "回撤优势", "回撤", "percent"),
    MetricDefinition("benchmark.sharpe_ratio", "基准夏普比率", "风险调整收益"),
    MetricDefinition("strategy.sharpe_ratio", "策略夏普比率", "风险调整收益"),
    MetricDefinition("benchmark.sortino_ratio", "基准索提诺比率", "风险调整收益"),
    MetricDefinition("strategy.sortino_ratio", "策略索提诺比率", "风险调整收益"),
    MetricDefinition("relative.excess_sharpe", "超额夏普比率", "相对收益"),
    MetricDefinition("relative.excess_sortino", "超额索提诺比率", "相对收益"),
    MetricDefinition("relative.excess_nav", "超额净值", "相对收益", "number"),
)


def get_metric_definition(key: str) -> MetricDefinition | None:
    return next((definition for definition in METRIC_REGISTRY if definition.key == key), None)
