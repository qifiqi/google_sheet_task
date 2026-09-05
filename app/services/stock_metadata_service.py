"""Stock metadata persistence helpers."""

from __future__ import annotations

import json
from typing import Any

from app.repositories import stock_metadata_repository
from app.utils.database import transaction_required
from app.utils.logger import get_logger
from app.utils.market import (
    infer_market_type,
    normalize_market_type,
    normalize_stock_code,
    strip_stock_code_suffix,
)


logger = get_logger(__name__)


def _strip_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_market_type(value: Any) -> str:
    normalized = normalize_market_type(value)
    return "us" if normalized == "en" else (normalized or "")


def normalize_stock_payload(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    stock_code = _strip_text(item.get("stock_code") or item.get("code")).upper()
    stock_name = _strip_text(item.get("stock_name") or item.get("name") or item.get("shortName"))
    if not stock_code or not stock_name:
        return {}
    raw_market_type = item.get("market_type") or item.get("marketType") or item.get("market")
    market_type = _normalize_market_type(raw_market_type)
    if not market_type:
        market_type = "cn" if infer_market_type(stock_code) == "cn" else "us"
    exchange_market = _strip_text(item.get("exchange_market") or item.get("market") or item.get("jys"))
    stock_code = normalize_stock_code(stock_code, market_type, exchange_market)
    security_type_name = _strip_text(item.get("security_type_name") or item.get("securityTypeName"))
    source = _strip_text(item.get("source") or "unknown")
    raw_payload = item.get("raw") if "raw" in item else item
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market_type": market_type,
        "exchange_market": exchange_market,
        "security_type_name": security_type_name,
        "source": source,
        "raw_json": json.dumps(raw_payload, ensure_ascii=False, default=str),
    }


def upsert_stock_metadata_in_session(stock_item: Any) -> dict | None:
    """会话内 upsert（不提交；提交由调用方/transaction_required 负责）。"""
    payload = normalize_stock_payload(stock_item)
    if not payload:
        return None
    record = stock_metadata_repository.upsert(payload, commit=False)
    logger.debug("已同步股票元数据: %s %s", payload["stock_code"], payload["stock_name"])
    return record


def lookup_stock_metadata(stock_code: Any, market_type: Any = None) -> dict[str, Any]:
    code = _strip_text(stock_code).upper()
    if not code:
        return {}
    normalized_market_type = _normalize_market_type(market_type) or (
        "cn" if infer_market_type(code) == "cn" else "us"
    )
    code = normalize_stock_code(code, normalized_market_type)
    record = stock_metadata_repository.get(code, normalized_market_type)
    # 不迁移历史表时，读取路径兼容旧的无后缀代码；新写入仍使用标准代码。
    if not record:
        legacy_code = strip_stock_code_suffix(code)
        if legacy_code != code:
            record = stock_metadata_repository.get(legacy_code, normalized_market_type)
    return record or {}


@transaction_required
def upsert_stock_metadata(stock_item: Any) -> dict | None:
    return upsert_stock_metadata_in_session(stock_item)


def bulk_upsert_stock_metadata(items: list[Any]) -> int:
    count = 0
    for item in items or []:
        if upsert_stock_metadata_in_session(item):
            count += 1
    return count
