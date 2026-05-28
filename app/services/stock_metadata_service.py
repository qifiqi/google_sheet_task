"""Stock metadata persistence helpers."""

from __future__ import annotations

import json
from typing import Any

from app.extensions import db
from app.models import StockMetadata
from app.utils.database import transaction_required
from app.utils.logger import get_logger


logger = get_logger(__name__)


def _strip_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_market_type(value: Any) -> str:
    text = _strip_text(value).lower()
    if text in {"cn", "a", "a股", "ashare", "china"}:
        return "cn"
    if text in {"us", "en", "美股", "usa"}:
        return "us"
    return ""


def normalize_stock_payload(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    stock_code = _strip_text(item.get("stock_code") or item.get("code")).upper()
    stock_name = _strip_text(item.get("stock_name") or item.get("name") or item.get("shortName"))
    if not stock_code or not stock_name:
        return {}
    market_type = _normalize_market_type(item.get("market_type") or item.get("marketType") or item.get("market"))
    if not market_type:
        market_type = "cn" if stock_code.isdigit() else "us"
    exchange_market = _strip_text(item.get("exchange_market") or item.get("market") or item.get("jys"))
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


def upsert_stock_metadata_in_session(stock_item: Any) -> StockMetadata | None:
    payload = normalize_stock_payload(stock_item)
    if not payload:
        return None

    market_type = payload["market_type"]
    query = StockMetadata.query.filter(StockMetadata.stock_code == payload["stock_code"])
    query = query.filter(StockMetadata.market_type == market_type)

    record = query.order_by(StockMetadata.updated_at.desc(), StockMetadata.id.desc()).first()
    if record is None:
        record = StockMetadata(**payload)
        db.session.add(record)
    else:
        for key, value in payload.items():
            setattr(record, key, value)

    logger.debug("已同步股票元数据: %s %s", payload["stock_code"], payload["stock_name"])
    return record


def lookup_stock_metadata(stock_code: Any, market_type: Any = None) -> dict[str, Any]:
    code = _strip_text(stock_code).upper()
    if not code:
        return {}
    normalized_market_type = _normalize_market_type(market_type) or ("cn" if code.isdigit() else "us")
    record = (
        StockMetadata.query
        .filter(StockMetadata.stock_code == code, StockMetadata.market_type == normalized_market_type)
        .order_by(StockMetadata.updated_at.desc(), StockMetadata.id.desc())
        .first()
    )
    if not record:
        return {}
    return record.to_dict()


@transaction_required
def upsert_stock_metadata(stock_item: Any) -> StockMetadata | None:
    return upsert_stock_metadata_in_session(stock_item)


def bulk_upsert_stock_metadata(items: list[Any]) -> int:
    count = 0
    for item in items or []:
        if upsert_stock_metadata_in_session(item):
            count += 1
    return count
