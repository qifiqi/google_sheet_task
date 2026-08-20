"""股票元数据的本地持久化与远程 CRUD 辅助函数。"""

from __future__ import annotations

import json
from typing import Any

from app.extensions import db
from app.models import StockMetadata
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.utils.database import transaction_required
from app.utils.logger import get_logger


logger = get_logger(__name__)

# 仅用于按 ID 读取和单条保存；业务键查询/批量 upsert 暂无远端筛选接口支撑。
_remote_repository = StockMetadataRepository()


def _strip_text(value: Any) -> str:
    """将任意输入转换为去除首尾空白的文本。"""
    return str(value or "").strip()


def _normalize_market_type(value: Any) -> str:
    """将多种市场别名归一为股票元数据使用的市场代码。"""
    text = _strip_text(value).lower()
    if text in {"cn", "a", "a股", "ashare", "china"}:
        return "cn"
    if text in {"us", "en", "美股", "usa"}:
        return "us"
    return ""


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
    """通过远程 CRUD 保存一条股票元数据。

    更新已有记录时调用方必须提供远端主键。按业务键查询和 upsert 依赖服务端
    筛选接口，当前刻意不以拉取全表的方式模拟，仍保留本地实现。
    """
    payload = normalize_stock_payload(item)
    if not payload:
        raise ValueError("股票元数据不能为空")
    if isinstance(item, dict) and item.get("id") is not None:
        payload["id"] = int(item["id"])
    return _remote_repository.save_metadata(payload)


def upsert_stock_metadata_in_session(stock_item: Any) -> StockMetadata | None:
    """按股票代码和市场类型在本地事务中 upsert，供批量同步流程使用。"""
    payload = normalize_stock_payload(stock_item)
    if not payload:
        return None

    stock_code = payload["stock_code"]
    market_type = payload["market_type"]

    for pending in db.session.new:
        if not isinstance(pending, StockMetadata):
            continue
        if pending.stock_code == stock_code and pending.market_type == market_type:
            for key, value in payload.items():
                setattr(pending, key, value)
            logger.debug("已同步待提交股票元数据: %s %s", stock_code, payload["stock_name"])
            return pending

    query = StockMetadata.query.filter(StockMetadata.stock_code == stock_code)
    query = query.filter(StockMetadata.market_type == market_type)

    with db.session.no_autoflush:
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


@transaction_required
def upsert_stock_metadata(stock_item: Any) -> StockMetadata | None:
    """写入或更新一条股票元数据记录。"""
    return upsert_stock_metadata_in_session(stock_item)


def bulk_upsert_stock_metadata(items: list[Any]) -> int:
    """批量写入股票元数据，并返回成功处理的记录数。"""
    count = 0
    for item in items or []:
        if upsert_stock_metadata_in_session(item):
            count += 1
    return count
