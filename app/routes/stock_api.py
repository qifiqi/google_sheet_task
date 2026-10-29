from flask import Blueprint, request

from app.exceptions import ValidationError
from app.schemas.stock import MINUTE_CAPABLE_DATA_SOURCES, MINUTE_KLINE_TYPES, StockKlineQuerySchema
from app.services.kline_service import KlineService
from app.services.stock_search_service import StockSearchService
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.kline_adjustment import normalize_kline_adjustment
from app.utils.request_parsing import parse_query

stock_api_bp = Blueprint("stock_api", __name__)

# KlineService 内部持有上游会话（requests.Session / StockClient），请求间复用。
_kline_service: KlineService | None = None


def _get_kline_service() -> KlineService:
    global _kline_service
    if _kline_service is None:
        _kline_service = KlineService()
    return _kline_service


# K线行对外字段白名单（KlineService 标准行的投影；stock_date 单独取根级时间）。
KLINE_ROW_FIELDS = (
    "open",
    "close",
    "high",
    "low",
    "volume",
    "amount",
    "vwap",
    "amplitude",
    "pct_change",
    "change",
    "turnover_rate",
    "data_source",
)


@stock_api_bp.route("/klines", methods=["GET"])
@login_required
def get_klines():
    """K线查询接口：按数据源拉取标准K线行，供K线页面表格与图表使用。"""
    query = parse_query(StockKlineQuerySchema)
    if query.kline_type in MINUTE_KLINE_TYPES and query.data_source not in MINUTE_CAPABLE_DATA_SOURCES:
        raise ValidationError("该数据源仅支持日K线；分钟周期请选择东方财富（dfcf）或腾讯（qq）数据源")

    # 前端直发 dfcf 数字复权码（0/1/2），归一为内部英文词：tdx 与内置库沉淀只认
    # forward/back 词表；None 不强转（akshare 缺省不复权、qq 缺省前复权，语义各异）。
    adjust_type = normalize_kline_adjustment(query.adjust_type) if query.adjust_type else None

    rows = _get_kline_service().get_kline_data(
        query.stock_code,
        query.market_type or "cn",
        query.limit,
        data_source=query.data_source,
        kline_type=query.kline_type,
        adjust_type=adjust_type,
        exchange_market=query.exchange_market,
        stock_name=query.stock_name,
    )
    # 分钟行的 stock_date 归属到日，展示用 stock_datetime（根级时间）优先。
    data = [
        {
            "stock_date": row.get("stock_datetime") or row.get("stock_date"),
            **{field: row.get(field) for field in KLINE_ROW_FIELDS},
        }
        for row in rows
    ]
    # data_source 取行内实际生效值（akshare 等源按市场自动回退 dfcf 时如实反映）。
    last_row = rows[-1] if rows else {}
    return success(data={
        "stock_code": last_row.get("stock_code") or query.stock_code,
        "stock_name": last_row.get("stock_name") or (query.stock_name or ""),
        "data_source": last_row.get("data_source") or query.data_source,
        "kline_type": query.kline_type,
        "adjust_type": adjust_type,
        "rows": data,
    })


@stock_api_bp.route("/search-stocks", methods=["GET"])
@login_required
def search_stocks():
    """股票搜索查询接口，不参与任务创建和 Sheet 占用检查。"""
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=10, type=int) or 10
    page_size = max(1, min(page_size, 20))

    # ValidationError→400、上游不可用 RuntimeError→ServiceError(502)，
    # 均由全局处理器渲染；上游错误文本不透传客户端。
    results = StockSearchService().search_stocks(
        keyword,
        # 搜索接口展示所有市场；市场类型仅用于任务侧的精确解析。
        market_type=None,
        page_size=page_size,
    )
    StockSearchService.save_metadata(results)

    return success(data={
        "keyword": keyword,
        "market_type": None,
        "results": results,
    })
