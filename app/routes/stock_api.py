from flask import Blueprint, request

from app.exceptions import BadRequestError, ServiceError
from app.services.stock_search_service import StockSearchService
from app.utils.api_response import success
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
        raise BadRequestError(str(exc))
    except RuntimeError as exc:
        # 上游搜索服务不可用，保持原有 502 语义。
        raise ServiceError(str(exc), http_status=502)

    return success(data={
        "keyword": keyword,
        "market_type": None,
        "results": results,
    })
