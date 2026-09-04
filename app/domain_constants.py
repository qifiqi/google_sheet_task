"""Shared domain enums and normalization helpers."""

from enum import Enum

from app.utils.market import MARKET_DEFAULT_COMMISSIONS, MARKET_LABELS, infer_market_type


class GoogleSheetTableType(str, Enum):
    C3 = "c3"
    C4 = "c4"
    C5 = "c5"
    C7 = "c7"
    BACKTEST_TRAINING = "backtest_training"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        raw = (value or "").strip().lower()
        if raw == "c31":
            raw = cls.C3.value
        valid_values = {item.value for item in cls}
        return raw if raw in valid_values else default

    @classmethod
    def choices(cls):
        labels = {
            cls.C3: "C3", cls.C4: "C4", cls.C5: "C5", cls.C7: "C7",
            cls.BACKTEST_TRAINING: "单品回测",
        }
        return [{"value": item.value, "label": labels[item]} for item in cls]


class StockMarketType(str, Enum):
    CN = "cn"
    EN = "en"
    CA = "ca"
    KR = "kr"
    JP = "jp"
    HK = "hk"
    UK = "uk"
    FR = "fr"
    DE = "de"
    SG = "sg"
    AU = "au"
    MY = "my"

    @classmethod
    def choices(cls):
        return [{
            "value": item.value,
            "label": MARKET_LABELS[item.value],
            "default_commission": MARKET_DEFAULT_COMMISSIONS[item.value],
        } for item in cls]


class GoogleSheetTokenTaskType(str, Enum):
    GOOGLE_SHEET = "google_sheet"
    BACKTEST_TRAINING = "backtest_training"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        raw = (value or "").strip().lower()
        valid_values = {item.value for item in cls}
        return raw if raw in valid_values else default

    @classmethod
    def choices(cls):
        return [
            {"value": cls.GOOGLE_SHEET.value, "label": "Google Sheet"},
            {"value": cls.BACKTEST_TRAINING.value, "label": "Backtest Training"},
        ]


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        raw = (value or "").strip().lower()
        valid_values = {item.value for item in cls}
        return raw if raw in valid_values else default

    @classmethod
    def choices(cls):
        labels = {cls.PENDING: "待执行", cls.RUNNING: "运行中", cls.COMPLETED: "已完成", cls.CANCELLED: "已取消", cls.ERROR: "错误"}
        return [{"value": item.value, "label": labels[item]} for item in cls]

    @classmethod
    def editable_choices(cls):
        return [item for item in cls.choices() if item["value"] in {cls.PENDING.value, cls.COMPLETED.value, cls.CANCELLED.value, cls.ERROR.value}]


class TaskType(str, Enum):
    GOOGLE_SHEET = "google_sheet"
    GOOGLE_SHEET_C4 = "google_sheet_C4"
    GOOGLE_SHEET_C5 = "google_sheet_C5"
    GOOGLE_SHEET_C7 = "google_sheet_C7"
    BACKTEST_TRAINING = "backtest_training"
    BACKTEST_MULTI_PRODUCT = "backtest_multi_product"
    MODEL_SUMMARY_REBUILD = "model_summary_rebuild"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        aliases = {
            "google_sheet": cls.GOOGLE_SHEET.value, "google_sheet_c3": cls.GOOGLE_SHEET.value,
            "google_sheet_c31": cls.GOOGLE_SHEET.value, "google_sheet_c4": cls.GOOGLE_SHEET_C4.value,
            "google_sheet_c5": cls.GOOGLE_SHEET_C5.value, "google_sheet_c7": cls.GOOGLE_SHEET_C7.value,
            "backtest": cls.BACKTEST_TRAINING.value, "backtest_training": cls.BACKTEST_TRAINING.value,
            "backtest_multi": cls.BACKTEST_MULTI_PRODUCT.value, "multi_product_backtest": cls.BACKTEST_MULTI_PRODUCT.value,
            "backtest_multi_product": cls.BACKTEST_MULTI_PRODUCT.value, "model_summary_rebuild": cls.MODEL_SUMMARY_REBUILD.value,
        }
        return aliases.get((value or "").strip().lower(), default)

    @classmethod
    def choices(cls, include_system=False):
        labels = {cls.GOOGLE_SHEET: "Google Sheet C3", cls.GOOGLE_SHEET_C4: "Google Sheet C4", cls.GOOGLE_SHEET_C5: "Google Sheet C5", cls.GOOGLE_SHEET_C7: "Google Sheet C7", cls.BACKTEST_TRAINING: "单品回测", cls.BACKTEST_MULTI_PRODUCT: "多品回测", cls.MODEL_SUMMARY_REBUILD: "汇总索引重建"}
        return [{"value": item.value, "label": labels[item]} for item in cls if include_system or item != cls.MODEL_SUMMARY_REBUILD]


def google_sheet_registry_scope(table_type: str | None) -> str:
    normalized = GoogleSheetTableType.normalize(table_type, GoogleSheetTableType.C3.value)
    return "c_series" if normalized in {"c3", "c4", "c5", "c7"} else normalized


def summary_market_type(stock_code: str | None) -> str:
    return "cn" if infer_market_type(stock_code) == "cn" else "us"
