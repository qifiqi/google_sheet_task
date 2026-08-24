"""股票元数据的远程 CRUD 辅助函数。"""

from __future__ import annotations

import json
from typing import Any

from app.models import StockMetadata
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.utils.logger import get_logger
from app.utils.market import normalize_market_type


logger = get_logger(__name__)

# 所有写入统一通过远端 ModifyOrAdd；重复约束由远端接口处理。
_remote_repository = StockMetadataRepository()


def _strip_text(value: Any) -> str:
    """将任意输入转换为去除首尾空白的文本。"""
    return str(value or "").strip()


def _normalize_market_type(value: Any) -> str:
    normalized = normalize_market_type(value)
    return "us" if normalized == "en" else (normalized or "")


def normalize_stock_payload(item: Any) -> dict[str, Any]:
    """将不同股票搜索来源的字段整理为统一元数据结构。"""
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


def get_stock_metadata_by_id(record_id: int) -> dict[str, Any] | None:
    """通过远程 CRUD 按主键读取一条股票元数据。"""
    return _remote_repository.get(int(record_id))


def save_stock_metadata(item: Any) -> dict[str, Any]:
    """通过远程 ModifyOrAdd 保存一条股票元数据。"""
    payload = normalize_stock_payload(item)
    if not payload:
        raise ValueError("股票元数据不能为空")
    if isinstance(item, dict) and item.get("id") is not None:
        payload["id"] = int(item["id"])
    return _remote_repository.save_metadata(payload)


def upsert_stock_metadata_in_session(stock_item: Any) -> dict[str, Any] | None:
    """兼容旧调用名称，实际通过远程 ModifyOrAdd 写入。"""
    payload = normalize_stock_payload(stock_item)
    if not payload:
        return None
    result = _remote_repository.save_metadata(payload)
    logger.debug("已通过远程接口同步股票元数据: %s %s", payload["stock_code"], payload["stock_name"])
    return result


def lookup_stock_metadata(stock_code: Any, market_type: Any = None) -> dict[str, Any]:
    """按业务键从本地库查询最新元数据；远端暂不具备等价筛选接口。"""
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


def upsert_stock_metadata(stock_item: Any) -> dict[str, Any] | None:
    """兼容旧调用入口，写入统一通过远程 CRUD。"""
    return upsert_stock_metadata_in_session(stock_item)


def bulk_upsert_stock_metadata(items: list[Any]) -> int:
    """批量写入股票元数据，并返回成功处理的记录数。"""
    count = 0
    for item in items or []:
        if upsert_stock_metadata_in_session(item):
            count += 1
    return count
