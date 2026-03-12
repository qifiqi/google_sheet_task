from __future__ import annotations

from copy import deepcopy
from typing import Any


# 以 C5 为统一契约基准，C4 走兼容映射，默认版暂时保留原结构。
UNIFIED_C5_DEFAULTS = {
    "task_type": "google_sheet_C5",
    "token_type": "file",
    "token_file": "data/token.json",
    "token_json": "",
    "proxy_url": None,
    "count_mode": "n_plus_1",
    "price_mode": "kp_price",
    "market_type": "cn",
    "date_range_mode": ["full"],
    "start_date": None,
    "end_date": None,
    "parameters": [],
    "sheets": [],
}


def _normalize_date_range_mode(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return ["full"]


def _normalize_sheets(config: dict[str, Any]) -> list[dict[str, str]]:
    raw_sheets = config.get("sheets")
    sheets: list[dict[str, str]] = []

    if isinstance(raw_sheets, list):
        for item in raw_sheets:
            if not isinstance(item, dict):
                continue
            sheet = {
                "spreadsheet_id": str(item.get("spreadsheet_id") or "").strip(),
                "sheet_name": str(item.get("sheet_name") or "").strip(),
                "title": str(item.get("title") or "").strip(),
            }
            if sheet["spreadsheet_id"] or sheet["sheet_name"] or sheet["title"]:
                sheets.append(sheet)

    # 兼容旧结构：顶层 spreadsheet_id / sheet_name 自动下沉到 sheets[0]。
    if not sheets:
        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        sheet_name = str(config.get("sheet_name") or "").strip()
        title = str(config.get("title") or "").strip()
        if spreadsheet_id or sheet_name or title:
            sheets.append(
                {
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_name": sheet_name,
                    "title": title,
                }
            )

    return sheets


def normalize_task_config(config: dict[str, Any], task_type: str | None = None) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")

    effective_task_type = task_type or config.get("task_type") or "google_sheet"

    # 默认版先保持原结构，避免一次性改动影响既有执行逻辑。
    if effective_task_type == "google_sheet":
        normalized = deepcopy(config)
        normalized["task_type"] = "google_sheet"
        return normalized

    # C4 / C5 统一向 C5-like 结构收敛，便于后续前后端共用 schema。
    normalized = deepcopy(UNIFIED_C5_DEFAULTS)
    normalized.update(config)
    normalized["task_type"] = effective_task_type
    normalized["token_type"] = str(normalized.get("token_type") or "file").strip() or "file"
    normalized["token_file"] = str(normalized.get("token_file") or "data/token.json").strip()
    normalized["token_json"] = str(normalized.get("token_json") or "")
    normalized["proxy_url"] = normalized.get("proxy_url") or None
    normalized["count_mode"] = str(normalized.get("count_mode") or "n_plus_1").strip() or "n_plus_1"
    normalized["price_mode"] = str(normalized.get("price_mode") or "kp_price").strip() or "kp_price"
    normalized["market_type"] = str(normalized.get("market_type") or "cn").strip() or "cn"
    normalized["date_range_mode"] = _normalize_date_range_mode(normalized.get("date_range_mode"))
    normalized["start_date"] = normalized.get("start_date") or None
    normalized["end_date"] = normalized.get("end_date") or None
    normalized["parameters"] = normalized.get("parameters") if isinstance(normalized.get("parameters"), list) else []
    normalized["sheets"] = _normalize_sheets(normalized)
    return normalized


def validate_task_config(config: dict[str, Any], task_type: str | None = None) -> None:
    effective_task_type = task_type or config.get("task_type") or "google_sheet"

    # 默认版按现有单表结构校验，避免误伤存量逻辑。
    if effective_task_type == "google_sheet":
        required_fields = ["spreadsheet_id", "sheet_name", "parameters"]
        missing = [field for field in required_fields if not config.get(field)]
        if missing:
            raise ValueError(f"missing required config fields: {', '.join(missing)}")
        if not isinstance(config.get("parameters"), list):
            raise ValueError("parameters must be a list")
        return

    token_type = config.get("token_type")
    if token_type not in {"file", "json"}:
        raise ValueError("token_type must be 'file' or 'json'")

    if token_type == "file" and not config.get("token_file"):
        raise ValueError("token_file is required when token_type=file")
    if token_type == "json" and not config.get("token_json"):
        raise ValueError("token_json is required when token_type=json")

    parameters = config.get("parameters")
    if not isinstance(parameters, list):
        raise ValueError("parameters must be a list")

    sheets = config.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("sheets must be a non-empty list")

    for index, sheet in enumerate(sheets, start=1):
        if not isinstance(sheet, dict):
            raise ValueError(f"sheets[{index}] must be an object")
        if not str(sheet.get("spreadsheet_id") or "").strip():
            raise ValueError(f"sheets[{index}].spreadsheet_id is required")
        if not str(sheet.get("sheet_name") or "").strip():
            raise ValueError(f"sheets[{index}].sheet_name is required")
