"""股票查询与证券解析的统一服务。"""

from __future__ import annotations

import re
from typing import Any

from app.services.stock_metadata_service import bulk_upsert_stock_metadata
from app.utils.dfcf_api import DFCJStockApi
from app.utils.market import (
    MARKET_LABELS,
    market_type_from_eastmoney,
    normalize_market_type,
    normalize_stock_code,
    strip_stock_code_suffix,
)


class StockSearchService:
    """封装东方财富搜索结果，供 API 与任务 K 线流程共用。"""

    def __init__(self, dfcf_api: Any | None = None):
        self.dfcf_api = dfcf_api or DFCJStockApi()

    def search_stocks(
        self,
        keyword: str,
        *,
        market_type: str | None = None,
        page_size: int = 10,
    ) -> list[dict[str, Any]]:
        keyword = str(keyword or "").strip()
        requested_market = self._normalize_requested_market(market_type)
        if not keyword:
            return []

        page_size = max(1, min(int(page_size or 10), 20))
        # 东方财富搜索不识别项目统一后缀，调用前还原为其原生代码。
        raw_results = self.dfcf_api.get_search_list_by_stock_code(
            strip_stock_code_suffix(keyword), page_size
        )
        if isinstance(raw_results, dict):
            raise RuntimeError(raw_results.get("error") or "股票搜索失败")

        results = [
            item for raw in raw_results or []
            if (item := self._normalize_result(raw))
        ]
        if requested_market:
            results = [item for item in results if item["market_type"] == requested_market]
        return results

    def resolve_stock(self, stock_code: str, market_type: str) -> dict[str, Any]:
        """按代码和市场精确解析证券，避免任务误取同名或跨市场标的。"""
        code = str(stock_code or "").strip().upper()
        requested_market = self._normalize_requested_market(market_type)
        if not code:
            raise ValueError("股票代码不能为空")
        if not requested_market:
            raise ValueError("任务市场类型不能为空")

        source_code = strip_stock_code_suffix(code)
        results = self.search_stocks(source_code, market_type=requested_market, page_size=20)
        result = next(
            (
                item for item in results
                if self._codes_match(item["code"], code, requested_market)
            ),
            None,
        )
        if not result:
            market_label = MARKET_LABELS.get(requested_market, requested_market)
            raise ValueError(
                f"未找到{market_label}（{requested_market}）市场股票代码 {code}。"
                "请确认代码和市场类型一致；港股代码可使用 0700 或 00700。"
            )
        if not result["exchange_market"]:
            raise ValueError(f"股票{code}搜索结果缺少交易市场编码")
        return result

    @staticmethod
    def save_metadata(results: list[dict[str, Any]]) -> None:
        """通过远程 CRUD 持久化 API 查询结果。"""
        bulk_upsert_stock_metadata([
            {
                "stock_code": item["code"],
                "stock_name": item["name"],
                "market_type": item["market_type"],
                "exchange_market": item["exchange_market"],
                "security_type_name": item["security_type_name"],
                "source": item["source"],
                "raw": item,
            }
            for item in results
            if item["market_type"]
        ])

    @staticmethod
    def _normalize_requested_market(value: str | None) -> str | None:
        if value in (None, ""):
            return None
        normalized = normalize_market_type(value)
        if not normalized:
            raise ValueError("market_type 不支持该市场类型")
        return normalized

    @staticmethod
    def _strip_html_tags(value: Any) -> str:
        return re.sub(r"<[^>]+>", "", str(value or "")).strip()

    @staticmethod
    def _codes_match(left: str, right: str, market_type: str) -> bool:
        """比较业务代码；港股兼容东方财富五位代码与 Yahoo 四位代码。"""
        left_code = normalize_stock_code(left, market_type)
        right_code = normalize_stock_code(right, market_type)
        if left_code == right_code:
            return True
        left_base = strip_stock_code_suffix(left_code)
        right_base = strip_stock_code_suffix(right_code)
        if market_type != "hk" or not left_base.isdigit() or not right_base.isdigit():
            return False
        return left_base.lstrip("0").zfill(4) == right_base.lstrip("0").zfill(4)

    def _normalize_result(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict) or raw.get("status") not in (10, "10", None):
            return None
        code = self._strip_html_tags(raw.get("code"))
        if not code:
            return None
        exchange_market = self._strip_html_tags(raw.get("market"))
        security_type_name = self._strip_html_tags(raw.get("securityTypeName"))
        market_type = normalize_market_type(raw.get("marketType")) or market_type_from_eastmoney(
            exchange_market,
            security_type_name,
        )
        name = self._strip_html_tags(raw.get("shortName") or raw.get("name"))
        normalized_code = normalize_stock_code(code, market_type, exchange_market)
        return {
            "source": raw.get("source"),
            "code": normalized_code,
            "name": name,
            "security_type_name": security_type_name,
            "market": exchange_market,
            "exchange_market": exchange_market,
            "market_type": market_type,
            "is_exact_match": bool(raw.get("isExactMatch")),
            "label": " · ".join(part for part in [normalized_code, name, security_type_name] if part),
            "status": raw.get("status"),
            "inner_code": raw.get("innerCode"),
            "pinyin": raw.get("pinyin"),
            "security_type": raw.get("securityType"),
            "small_type": raw.get("smallType"),
            "flag": raw.get("flag"),
            "ext_small_type": raw.get("extSmallType"),
            "quote_id": raw.get("quoteId"),
            "unified_code": raw.get("unifiedCode"),
            "jys": raw.get("jys"),
            "classify": raw.get("classify"),
        }
