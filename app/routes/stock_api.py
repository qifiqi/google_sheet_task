from flask import Blueprint, jsonify, request

from app.services.stock_search_service import StockSearchService
from app.utils.auth import login_required

stock_api_bp = Blueprint("stock_api", __name__)


@stock_api_bp.route("/search-stocks", methods=["GET"])
@login_required
def search_stocks():
    """股票搜索查询接口，不参与任务创建和 Sheet 占用检查。"""
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=10, type=int) or 10
    page_size = max(1, min(page_size, 20))

    try:
        results = StockSearchService().search_stocks(
            keyword,
            # 搜索接口展示所有市场；市场类型仅用于任务侧的精确解析。
            market_type=None,
            page_size=page_size,
        )
        StockSearchService.save_metadata(results)
    except ValueError as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 400
    except RuntimeError as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 502

    return jsonify({
        "status": "success",
        "keyword": keyword,
        "market_type": None,
        "results": results,
    })
