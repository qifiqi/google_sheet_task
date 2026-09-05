"""回测域请求 Schema。"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import APIModel


class CalculateRatiosSchema(APIModel):
    ratios: list[Any]


class ImportExcelSchema(BaseModel):
    """multipart 文件上传不在 JSON body 校验域；
    文件存在性由路由检查（保留现状）。"""

    model_config = None


SINGLE_PRODUCT_REPORT_TYPE = "RPT-S"
MULTI_PRODUCT_REPORT_TYPE = "RPT-M"
REPORT_TYPES = {SINGLE_PRODUCT_REPORT_TYPE, MULTI_PRODUCT_REPORT_TYPE}
DEFAULT_REPORT_TITLE = "量化策略回测绩效分析报告"


class StrategyBacktestReportSchema(APIModel):
    """策略回测 Word 报告请求（自 app/dto 收编，统一 Pydantic 校验）。

    覆盖三种请求形态：
    - RPT-S：顶层三选一收益来源（returns / task_id / Google Sheet）；
    - RPT-M products 形态：每个产品各自三选一（服务端按任务构建的载荷走此分支）；
    - RPT-M group_key 形态：前端全局预览页直传 task_id + group_key + ratios，
      由 export_service 按任务构建 products 后再次过本 Schema。

    weighting_mode 仅承载取值，归一化由 portfolio_combiner 统一处理
    （schemas 不 import service）。
    """

    # 直接输入的累计收益序列，格式为 date、index_return、start_return。
    returns: list[dict[str, Any]] = []
    # 单品任务来源；return_series_id 在一个 task 有多条结果时用于精确指定。
    task_id: str | None = None
    return_series_id: int | None = Field(default=None, gt=0)
    # V2 Google Sheet 来源；spreadsheet_id 可以由 google_sheet_url 解析得到。
    google_sheet_url: str | None = None
    spreadsheet_id: str | None = None
    google_sheet_name: str | None = None
    # 以下字段用于控制报告名称、展示类型和产品权重。
    filename: str | None = None
    report_type: str = SINGLE_PRODUCT_REPORT_TYPE
    title: str = DEFAULT_REPORT_TITLE
    metadata: dict[str, Any] = {}
    products: list[dict[str, Any]] = []
    weight_allocation: dict[str, Any] | None = None
    weighting_mode: str = "daily_compound"
    # 市场阶段阈值交给 performance_analysis 的运行参数对象。
    runtime_params: dict[str, Any] = {}
    # group_key 形态专用字段（仅 export_service 消费，generate_word 不使用）。
    group_key: str | None = None
    ratios: Any = None

    @field_validator("report_type", mode="before")
    @classmethod
    def _normalize_report_type(cls, value):
        return str(value or SINGLE_PRODUCT_REPORT_TYPE).upper()

    @field_validator("title", mode="before")
    @classmethod
    def _empty_title_to_default(cls, value):
        return value or DEFAULT_REPORT_TITLE

    @field_validator("returns", "products", mode="before")
    @classmethod
    def _none_list_to_empty(cls, value):
        """对齐原 DTO 语义：显式 null 与缺失一样按空容器处理。"""
        return [] if value is None else value

    @field_validator("metadata", "runtime_params", mode="before")
    @classmethod
    def _none_dict_to_empty(cls, value):
        return {} if value is None else value

    @model_validator(mode="after")
    def _validate_report_request(self):
        if self.report_type not in REPORT_TYPES:
            raise ValueError("report_type 仅支持 RPT-S 或 RPT-M")

        if self.report_type == MULTI_PRODUCT_REPORT_TYPE:
            if self.products:
                # products 形态（服务端构建的载荷 / 直传多品）。
                if len(self.products) <= 1:
                    raise ValueError("RPT-M 报告必须传入至少 2 个产品")
                if self.returns or self.task_id or self.spreadsheet_id or self.google_sheet_url:
                    raise ValueError("RPT-M 的收益来源必须配置在每个 products 项中")
                for index, product in enumerate(self.products, start=1):
                    self._validate_source(product, product.get("returns") or [], label=f"products[{index}]")
                return self
            # group_key 形态（前端全局预览页直传，export_service 按任务构建 products）。
            if not self.task_id:
                raise ValueError("RPT-M 报告必须传入 task_id")
            if self.group_key in (None, ""):
                raise ValueError("RPT-M 报告必须传入 group_key")
            if not isinstance(self.ratios, list):
                raise ValueError("RPT-M 报告的 ratios 必须是数组")
            return self

        # RPT-S：产品仅用于权重/命名展示，收益来源仍在顶层三选一。
        if len(self.products) > 1:
            raise ValueError("RPT-S 报告最多传入 1 个产品")
        self._validate_source({
            "task_id": self.task_id,
            "return_series_id": self.return_series_id,
            "spreadsheet_id": self.spreadsheet_id,
            "google_sheet_url": self.google_sheet_url,
            "google_sheet_name": self.google_sheet_name,
        }, self.returns)
        return self

    @staticmethod
    def _validate_source(source: dict[str, Any], returns: Any, *, label: str = "请求") -> None:
        """三选一收益来源校验：returns、task_id、Google Sheet 必须且只能其一。"""
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
