"""策略回测 Word 报告请求 DTO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SINGLE_PRODUCT_REPORT_TYPE = "RPT-S"
MULTI_PRODUCT_REPORT_TYPE = "RPT-M"
REPORT_TYPES = {SINGLE_PRODUCT_REPORT_TYPE, MULTI_PRODUCT_REPORT_TYPE}
DEFAULT_FILENAME = "策略回测绩效分析报告.docx"
DEFAULT_TITLE = "量化策略回测绩效分析报告"


@dataclass(frozen=True, slots=True)
class StrategyBacktestReportRequestDTO:
    """Word 报告请求。

    单品与 V2 只能选择一种收益来源：直接 ``returns``、任务收益序列
    ``task_id``，或 Google Sheet。多品在每个 ``products`` 元素中选择一种来源，
    再由服务按产品比例合成组合收益序列。
    """

    # 直接输入的累计收益序列，格式为 date、index_return、start_return。
    returns: list[dict[str, Any]] = field(default_factory=list)
    # 单品任务来源；return_series_id 在一个 task 有多条结果时用于精确指定。
    task_id: str | None = None
    return_series_id: int | None = None
    # V2 Google Sheet 来源；spreadsheet_id 可以由 google_sheet_url 解析得到。
    google_sheet_url: str | None = None
    spreadsheet_id: str | None = None
    google_sheet_name: str | None = None
    # 以下字段用于控制报告名称、展示类型和产品权重。
    filename: str = DEFAULT_FILENAME
    report_type: str = SINGLE_PRODUCT_REPORT_TYPE
    title: str = "量化策略回测绩效分析报告"
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
        returns = payload.get("returns") or []
        if not isinstance(returns, list):
            raise ValueError("returns 必须是数组")
        metadata = payload.get("metadata")
        products = payload.get("products")
        runtime_params = payload.get("runtime_params")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata 必须是对象")
        if products is not None and not isinstance(products, list):
            raise ValueError("products 必须是数组")
        if any(not isinstance(product, dict) for product in products or []):
            raise ValueError("products 的每一项必须是对象")
        if runtime_params is not None and not isinstance(runtime_params, dict):
            raise ValueError("runtime_params 必须是对象")
        report_type = str(payload.get("report_type") or SINGLE_PRODUCT_REPORT_TYPE).upper()
        product_count = len(products or [])
        if report_type not in REPORT_TYPES:
            raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")
        if report_type == SINGLE_PRODUCT_REPORT_TYPE and product_count > 1:
            raise ValueError("RPT-S 报告最多传入 1 个产品")
        if report_type == MULTI_PRODUCT_REPORT_TYPE and product_count <= 1:
            raise ValueError("RPT-M 报告必须传入至少 2 个产品")
        if report_type == SINGLE_PRODUCT_REPORT_TYPE:
            cls._validate_source(payload, returns)
        else:
            if returns or payload.get("task_id") or payload.get("spreadsheet_id") or payload.get("google_sheet_url"):
                raise ValueError("RPT-M 的收益来源必须配置在每个 products 项中")
            for index, product in enumerate(products or [], start=1):
                cls._validate_source(product, product.get("returns") or [], label=f"products[{index}]")
        return cls(
            returns=returns,
            task_id=str(payload["task_id"]).strip() if payload.get("task_id") else None,
            return_series_id=cls._optional_int(payload.get("return_series_id"), "return_series_id"),
            google_sheet_url=str(payload["google_sheet_url"]).strip() if payload.get("google_sheet_url") else None,
            spreadsheet_id=str(payload["spreadsheet_id"]).strip() if payload.get("spreadsheet_id") else None,
            google_sheet_name=str(payload["google_sheet_name"]).strip() if payload.get("google_sheet_name") else None,
            filename=str(payload.get("filename") or DEFAULT_FILENAME),
            report_type=report_type,
            title=str(payload.get("title") or DEFAULT_TITLE),
            metadata=metadata or {},
            products=products or [],
            weight_allocation=payload.get("weight_allocation"),
            runtime_params=runtime_params or {},
        )

    @staticmethod
    def _optional_int(value: Any, field_name: str) -> int | None:
        if value in (None, ""):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是整数") from exc
        if parsed <= 0:
            raise ValueError(f"{field_name} 必须大于 0")
        return parsed

    @classmethod
    def _validate_source(cls, source: dict[str, Any], returns: Any, *, label: str = "请求") -> None:
        if not isinstance(returns, list):
            raise ValueError(f"{label}.returns 必须是数组")
        has_returns = bool(returns)
        has_task = bool(source.get("task_id"))
        has_sheet = bool(source.get("spreadsheet_id") or source.get("google_sheet_url"))
        if sum((has_returns, has_task, has_sheet)) != 1:
            raise ValueError(f"{label} 必须且只能指定 returns、task_id 或 Google Sheet 来源之一")
        if source.get("return_series_id") not in (None, "") and not has_task:
            raise ValueError(f"{label}.return_series_id 必须与 task_id 一起传入")
        if has_sheet and not str(source.get("google_sheet_name") or "").strip():
            raise ValueError(f"{label}.google_sheet_name 不能为空")
