"""回测域请求 Schema。"""

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import APIModel


class CalculateRatiosSchema(APIModel):
    ratios: list[Any]


SINGLE_PRODUCT_REPORT_TYPE = "RPT-S"
MULTI_PRODUCT_REPORT_TYPE = "RPT-M"
REPORT_TYPES = {SINGLE_PRODUCT_REPORT_TYPE, MULTI_PRODUCT_REPORT_TYPE}
DEFAULT_REPORT_TITLE = "量化策略回测绩效分析报告"
BENCHMARK_RATIO_BASE = 100.0


class IndexBenchmarkSchema(APIModel):
    """RPT-M 基准指数条目：产品代码 + 参与比例（百分比数值）。"""

    stock_code: str
    # 百分比数值（50 = 50%），(0, 100]；归一化见 _normalize_index_benchmarks。
    ratio: float


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
    # RPT-M 基准指数（产品代码 + 比例%，最多 3 条；空 = 默认组合index；
    # 同一产品可用不同比例选多次，作为不同基准列对比）。
    index_benchmarks: list[IndexBenchmarkSchema] = []
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

    @field_validator("index_benchmarks", mode="before")
    @classmethod
    def _normalize_index_benchmarks(cls, value):
        """基准条目归一：null 视为空选；比例兼容 50、"50%"、0.5（等价 50%）。

        语义 A（每指数各自带比例）：同一产品可用不同比例选多次作为不同
        基准列，仅代码+比例完全相同的重复条目去重；上限 3 条保证表格
        与图例可读。
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("index_benchmarks 必须是数组")
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, float]] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("index_benchmarks 每项必须是 {stock_code, ratio} 对象")
            code = str(item.get("stock_code") or "").strip()
            if not code:
                continue
            raw_ratio = str(item.get("ratio") if item.get("ratio") is not None else 100).strip()
            explicit_percent = raw_ratio.endswith("%")
            try:
                number = float(raw_ratio[:-1] if explicit_percent else raw_ratio)
            except ValueError as exc:
                raise ValueError(f"指数 {code} 的比例不是有效数字: {item.get('ratio')}") from exc
            if not math.isfinite(number) or number < 0:
                raise ValueError(f"指数 {code} 的比例必须是非负有限数")
            percent = number if (explicit_percent or number > 1) else number * 100
            if not 0 < percent <= BENCHMARK_RATIO_BASE:
                raise ValueError(f"指数 {code} 的比例必须在 (0, 100] 区间内")
            key = (code, percent)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"stock_code": code, "ratio": percent})
        if len(normalized) > 3:
            raise ValueError("基准指数最多支持选择 3 条")
        return normalized

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
                self._validate_index_benchmarks_unique_hit()
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

    def _validate_index_benchmarks_unique_hit(self) -> None:
        """基准代码必须唯一命中产品：0 命中是未知代码，多命中是同码歧义。

        同一代码可出现多条（不同比例），仅按唯一代码做命中校验。
        """
        if not self.index_benchmarks:
            return
        product_codes = [
            str(product.get("stock_code") or "").strip() for product in self.products
        ]
        for code in {item.stock_code for item in self.index_benchmarks}:
            hits = product_codes.count(code)
            if hits == 0:
                raise ValueError(f"指数代码 {code} 不在产品列表中")
            if hits > 1:
                raise ValueError(f"指数代码 {code} 命中多个产品，存在歧义，请检查产品配置")

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


class UpdateRatiosSchema(APIModel):
    """PUT /backtest-multi-product/api/global-preview/<task_id>/ratios。"""

    ratios: list[Any]


class ReturnSeriesExportSchema(APIModel):
    """POST /backtest-multi-product/api/global-preview/<task_id>/return-series。

    纯数据载荷：直查 t_param_task_results_return 返回累计收益序列；
    ratios 覆盖产品比例（未传用任务默认比例），group_key 过滤参数方案。
    净值/当天收益率/比例组合等全部由前端 Excel 公式计算，后端零派生。
    """

    ratios: list[Any] | None = None
    group_key: str | None = None


class PreviewGroupSchema(APIModel):
    """POST /global-preview/api/tasks/<task_id>/preview-group。"""

    result_ids: list[int] = []
