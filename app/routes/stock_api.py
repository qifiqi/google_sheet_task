import re

from flask import Blueprint, jsonify, request

from app.utils.dfcf_api import DFCJStockApi

stock_api_bp = Blueprint("stock_api", __name__)


def _strip_html_tags(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


@stock_api_bp.route("/search-stocks", methods=["GET"])
def search_stocks():
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=10, type=int) or 10
    page_size = max(1, min(page_size, 20))

    if len(keyword) < 1:
        return jsonify({
            "status": "success",
            "keyword": keyword,
            "results": [],
        })

    raw_results = DFCJStockApi().get_search_list_by_stock_code(keyword, page_size=page_size)
    if isinstance(raw_results, dict) and raw_results.get("error"):
        return jsonify({
            "status": "error",
            "message": raw_results.get("error") or "股票搜索失败",
        }), 502

    normalized_results = []
    for item in raw_results or []:
        if item.get("status") not in (10, "10", None):
            continue
        code = _strip_html_tags(item.get("code"))
        short_name = _strip_html_tags(item.get("shortName"))
        security_type_name = _strip_html_tags(item.get("securityTypeName"))
        market = item.get("market")
        if not code:
            continue
        normalized_results.append({
            "source": item.get("source"),
            "code": code,
            "name": short_name,
            "security_type_name": security_type_name,
            "market": market,
            "is_exact_match": bool(item.get("isExactMatch")),
            "label": " · ".join(part for part in [code, short_name, security_type_name] if part),
            "status": item.get("status"),
            "inner_code": item.get("innerCode"),
            "pinyin": item.get("pinyin"),
            "security_type": item.get("securityType"),
            "small_type": item.get("smallType"),
            "flag": item.get("flag"),
            "ext_small_type": item.get("extSmallType"),
            "quote_id": item.get("quoteId"),
            "market_type": item.get("marketType"),
            "unified_code": item.get("unifiedCode"),
            "jys": item.get("jys"),
            "classify": item.get("classify"),
        })

    return jsonify({
        "status": "success",
        "keyword": keyword,
        "results": normalized_results,
    })
