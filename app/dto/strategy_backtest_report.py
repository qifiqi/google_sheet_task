"""策略回测 Word 报告请求 DTO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyBacktestReportRequestDTO:
    """Word 报告接口入参；收益序列由调用方传入，指标由服务统一计算。"""

    # 核心收益数据，格式为 date、index_return、start_return 字段组成的数组。
    returns: list[dict[str, Any]]
    # 以下字段用于控制报告名称、展示类型和多产品权重。
    filename: str = "策略回测绩效分析报告.docx"
    report_type: str = "ZRPT"
    title: str = "量化策略回测绩效分析报告"
    report_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    products: list[dict[str, Any]] = field(default_factory=list)
    weight_allocation: dict[str, Any] | None = None
    # 市场阶段阈值交给 performance_analysis 的运行参数对象。
    runtime_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "StrategyBacktestReportRequestDTO":
        """校验并转换 HTTP JSON 请求，避免服务层直接依赖 Flask request。"""
        if not isinstance(payload, dict):
            raise ValueError("请求数据必须是 JSON 对象")
        returns = payload.get("returns")
        if not isinstance(returns, list) or not returns:
            raise ValueError("returns 必须是非空数组")
        metadata = payload.get("metadata")
        products = payload.get("products")
        runtime_params = payload.get("runtime_params")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata 必须是对象")
        if products is not None and not isinstance(products, list):
            raise ValueError("products 必须是数组")
        if runtime_params is not None and not isinstance(runtime_params, dict):
            raise ValueError("runtime_params 必须是对象")
        return cls(
            returns=returns,
            filename=str(payload.get("filename") or cls.filename),
            report_type=str(payload.get("report_type") or cls.report_type).upper(),
            title=str(payload.get("title") or cls.title),
            report_id=str(payload["report_id"]) if payload.get("report_id") else None,
            metadata=metadata or {},
            products=products or [],
            weight_allocation=payload.get("weight_allocation"),
            runtime_params=runtime_params or {},
        )
