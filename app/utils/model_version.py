"""模型版本唯一规范：内部 snake slug，显示层统一格式化。"""

from __future__ import annotations

from typing import Any

from app.utils.task_types import (
    TYPE_GOOGLE_SHEET,
    TYPE_GOOGLE_SHEET_C1_1,
    TYPE_GOOGLE_SHEET_C4,
    TYPE_GOOGLE_SHEET_C5,
    TYPE_GOOGLE_SHEET_C7,
)


MODEL_VERSION_LABELS = {
    "c3": "C3",
    "c4": "C4",
    "c5": "C5",
    "c7_0_2": "C7.0.2",
    "c7_0_3": "C7.0.3",
    "c1_1": "C1.1",
}

MODEL_VERSION_FAMILIES = {
    "c3": "C3",
    "c4": "C4",
    "c5": "C5",
    "c7_0_2": "C7",
    "c7_0_3": "C7",
    "c1_1": "C1.1",
}

# 任务类型（内部规范词汇，枚举派生）→ 模型版本 slug；c3/c31 为历史输入别名键。
TASK_TYPE_MODEL_VERSIONS = {
    TYPE_GOOGLE_SHEET: "c3",
    "google_sheet_c3": "c3",
    "google_sheet_c31": "c3",
    TYPE_GOOGLE_SHEET_C4: "c4",
    TYPE_GOOGLE_SHEET_C5: "c5",
    TYPE_GOOGLE_SHEET_C1_1: "c1_1",
}

_ALIASES = {
    "c3_0": "c3",
    "c4_0": "c4",
    "c5_0": "c5",
    "c7": "c7_0_2",
    "c1_1_0": "c1_1",
}


def normalize_model_version(value: Any) -> str | None:
    raw = str(value or "").strip().lower().replace("-", "_").replace(".", "_")
    if not raw:
        return None
    raw = _ALIASES.get(raw, raw)
    return raw if raw in MODEL_VERSION_LABELS else None


def resolve_model_version(task_type: str | None, sheet: Any = None) -> str:
    """运行时唯一解析入口：只读已落库的 sheets[].model_version。"""
    normalized_type = str(task_type or "").strip().lower()
    sheet_config = sheet if isinstance(sheet, dict) else {}
    version = normalize_model_version(sheet_config.get("model_version"))
    if version:
        return version
    if normalized_type == TYPE_GOOGLE_SHEET_C7:
        return "c7_0_2"
    return TASK_TYPE_MODEL_VERSIONS.get(normalized_type, "")


def infer_model_version(task_type: str | None, sheet: Any = None) -> str:
    """创建边界一次性推断并落库；运行时不得调用标题推断。"""
    version = resolve_model_version(task_type, sheet)
    if version:
        return version
    title = str((sheet or {}).get("title") or "").upper() if isinstance(sheet, dict) else ""
    if "C7.0.3" in title:
        return "c7_0_3"
    if "C7" in title:
        return "c7_0_2"
    if "C1.1" in title:
        return "c1_1"
    for family, candidate in (("C5", "c5"), ("C4", "c4"), ("C3", "c3")):
        if family in title:
            return candidate
    return ""


def normalize_sheets_model_versions(config: Any, task_type: str | None) -> Any:
    """创建/保存模板时补全 sheets[].model_version，之后运行时只读该字段。"""
    if not isinstance(config, dict):
        return config
    sheets = config.get("sheets")
    if isinstance(sheets, list):
        for sheet in sheets:
            if isinstance(sheet, dict) and not normalize_model_version(sheet.get("model_version")):
                version = infer_model_version(task_type, sheet)
                if version:
                    sheet["model_version"] = version
    products = config.get("products")
    if isinstance(products, list):
        for product in products:
            if not isinstance(product, dict):
                continue
            sheet = product.get("sheet")
            if isinstance(sheet, dict) and not normalize_model_version(sheet.get("model_version")):
                version = infer_model_version(task_type, sheet)
                if version:
                    sheet["model_version"] = version
    return config


def format_model_version(value: Any) -> str:
    normalized = normalize_model_version(value)
    if normalized:
        return MODEL_VERSION_LABELS[normalized]
    return str(value or "").strip().upper()


def model_family(value: Any) -> str:
    normalized = normalize_model_version(value)
    if normalized:
        return MODEL_VERSION_FAMILIES[normalized]
    return format_model_version(value)
