"""任务配置（Task.config）逐类型 Pydantic 模型（2026-10 配置结构统一）。

统一约定（唯一存储形态，无兼容分支）：
- Google Sheet 引用一律为 ``sheets: list[SheetRef]``：C3/C31 子任务与单品回测
  恰好 1 个元素，C4/C5/C7 多元素；多品回测因每个产品各有一张表，保留
  ``products[].sheet: SheetRef``（复用同一 SheetRef 定义）。
- 公共段（token / K线取数）经 mixin 复用，全部任务类型共享同一份字段定义。
- 模型声明所有已知业务键并做类型收口；``extra="allow"`` 保留执行期布局键
  （``c3_input_column_d``、``parameter_positions`` 等，多来自 SystemConfig
  合并兜底，任务 config 中仅偶尔出现），保证 model_dump 无损回写。

历史数据由 ``scripts/migrate_task_config_schema.py`` 一次性迁移到本文件定义的
形态；迁移后读取路径不再容忍旧形态（平铺 spreadsheet_id / 嵌套 sheet{}）。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

TASK_SHEET_NAME_DEFAULT = "data"


class SheetRef(BaseModel):
    """单个 Google Sheet 引用（全部任务类型共用的唯一引用形态）。"""

    model_config = ConfigDict(extra="allow")

    spreadsheet_id: str
    sheet_name: str = TASK_SHEET_NAME_DEFAULT
    title: str = ""
    # 单品回测占用校验键（occupancy.validate_backtest_training_sheet）；
    # 占用表主键可能以 int 直传，收口时统一保留原值
    google_sheet_id: str | int | None = None
    # C7 系列逐 sheet 版本标记（c7_0_2 / c7_0_3）
    c7_model_version: str | None = None

    @field_validator("sheet_name", "title", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: Any) -> Any:
        # 历史 C31 子任务存在 title=None 落库；统一收口为空串
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value

    @field_validator("spreadsheet_id")
    @classmethod
    def _require_spreadsheet_id(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("spreadsheet_id 不能为空")
        return value

    @field_validator("sheet_name")
    @classmethod
    def _default_sheet_name(cls, value: str) -> str:
        return value or TASK_SHEET_NAME_DEFAULT

    @field_validator("c7_model_version")
    @classmethod
    def _normalize_c7_version(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower()
        return value or None


class TokenRefFields(BaseModel):
    """Token 选择公共段（prepare_task_config 注入/消费）。"""

    model_config = ConfigDict(extra="allow")

    token_type: str | None = None
    token_id: str | int | None = None
    token_file: str | None = None
    token_json: str | None = None
    token_name: str | None = None
    token_selection_mode: str | None = None
    token_task_type: str | None = None


class KlineCommonFields(BaseModel):
    """K线取数公共段（C 系与回测系共享）。"""

    model_config = ConfigDict(extra="allow")

    market_type: str | None = None
    exchange_market: str | None = None
    price_mode: str | None = None
    kline_adjustment: str | None = None
    kline_data_source: str | None = None
    proxy_url: str | None = None


class _BaseTaskConfig(TokenRefFields, KlineCommonFields):
    """全部任务配置的公共底座。"""

    model_config = ConfigDict(extra="allow")

    stock_name: str | None = None
    # Google Sheet 占用表关联键（update_task_config 占用迁移对比）
    google_sheet_id: str | int | None = None


class _SingleSheetMixin(BaseModel):
    """sheets 恰好 1 个元素的约束（C3/C31 子任务、单品回测共享）。

    mixin 自身不声明 sheets 字段，check_fields=False 供子类继承生效。
    """

    @field_validator("sheets", check_fields=False)
    @classmethod
    def _single_sheet(cls, value: list[SheetRef]) -> list[SheetRef]:
        if len(value) != 1:
            raise ValueError("该任务类型只支持一个 Google Sheet（sheets 长度必须为 1）")
        return value


class C3TaskConfig(_SingleSheetMixin, _BaseTaskConfig):
    """C3 单表任务（含 C31 拆分出的子任务，task_type=google_sheet）。"""

    sheets: list[SheetRef]
    stock_code: str = ""
    year_n: str | None = None
    end_date: str | None = None
    parameters: list[Any] = []


class _CSeriesBase(_BaseTaskConfig):
    """C4/C5/C7 多表批量骨架公共段（count_mode/date_range 驱动 _expand_auto_year_parameters）。"""

    sheets: list[SheetRef]
    count_mode: str | None = None
    date_range_mode: list[Any] = []
    start_date: str | None = None
    end_date: str | None = None
    parameters: list[Any] = []

    @field_validator("sheets")
    @classmethod
    def _require_sheets(cls, value: list[SheetRef]) -> list[SheetRef]:
        if not value:
            raise ValueError("至少需要一张 Google Sheet（sheets 不能为空）")
        return value


class C4TaskConfig(_CSeriesBase):
    """C4 批量取价任务。"""


class C5TaskConfig(_CSeriesBase):
    """C5 批量校验任务（在 C4 段上增加 custom K线与随机价格段）。"""

    kline_source: str | None = None
    exclude_recent_years: list[Any] = []
    random_price_range: str | None = None
    random_group_count: int | None = None


class C7TaskConfig(C5TaskConfig):
    """C7 批量校验任务（版本标记在 sheets[].c7_model_version 上）。"""


class BacktestTrainingConfig(_SingleSheetMixin, _BaseTaskConfig):
    """单品回测训练任务（sheet 引用统一为 sheets[1]）。"""

    sheets: list[SheetRef]
    stock_code: str = ""
    end_date: str | None = None
    recent_years: list[Any] = []
    full_years: list[Any] = []
    include_full_year_range: bool | None = None
    excel_import: bool | None = None
    parameters: list[Any] = []


class ProductSpec(BaseModel):
    """多品回测的单产品规格（sheet 复用全局唯一 SheetRef 形态）。"""

    model_config = ConfigDict(extra="allow")

    product_index: int | None = None
    product_name: str | None = None
    stock_code: str = ""
    market_type: str | None = None
    exchange_market: str | None = None
    price_mode: str | None = None
    kline_adjustment: str | None = None
    kline_data_source: str | None = None
    ratio: str | None = None
    is_fixed: bool = False
    sheet: SheetRef
    parameters: list[Any] = []


class MultiProductConfig(_BaseTaskConfig):
    """多品回测任务。"""

    start_date: str | None = None
    end_date: str | None = None
    weighting_mode: str | None = None
    fixed_product_batch_id: str | None = None
    products: list[ProductSpec]

    @field_validator("products")
    @classmethod
    def _require_products(cls, value: list[ProductSpec]) -> list[ProductSpec]:
        if len(value) < 2:
            raise ValueError("多品数据回测至少需要 2 个产品")
        return value


# task_type → 配置模型（google_sheet_C31 是拆分器标记，不落 Task 行，无独立模型）
TASK_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "google_sheet": C3TaskConfig,
    "google_sheet_C3": C3TaskConfig,
    "google_sheet_C4": C4TaskConfig,
    "google_sheet_C5": C5TaskConfig,
    "google_sheet_C7": C7TaskConfig,
    "backtest_training": BacktestTrainingConfig,
    "backtest_multi_product": MultiProductConfig,
}


def get_task_config_model(task_type: str | None) -> type[BaseModel] | None:
    """按任务类型取配置模型；未知类型返回 None（不校验，保持原样透传）。"""
    if not task_type:
        return None
    return TASK_CONFIG_MODELS.get(str(task_type))


def validate_task_config_shape(task_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """按任务类型模型校验并输出规范 JSON 形态（模型层唯一出口）。

    校验失败抛 pydantic.ValidationError，由调用方决定业务语义（creation 转
    ValidationError，迁移脚本跳过登记）。
    """
    model_cls = get_task_config_model(task_type)
    if model_cls is None:
        return config
    validated = model_cls.model_validate(config)
    return validated.model_dump(mode="json", exclude_none=False)
