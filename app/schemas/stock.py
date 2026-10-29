"""股票搜索与 K 线查询域请求 Schema。"""

from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel

# K线周期（东财 klt 口径）：101 日 / 102 周 / 103 月；1/5/15/30/60 分钟。
KLINE_TYPE_LITERALS = Literal["1", "5", "15", "30", "60", "101", "102", "103"]
MINUTE_KLINE_TYPES = frozenset({"1", "5", "15", "30", "60"})
# 数据源枚举与 kline_service.VALID_DATA_SOURCES 逐值等价（eastmoney/db 别名由服务端归一）。
DATA_SOURCE_LITERALS = Literal["dfcf", "qq", "akshare", "yahoo", "tdx", "database"]
# 分钟周期仅东方财富/腾讯源提供；周/月K在其余源（akshare/yahoo/tdx/内置库）由日线聚合推算。
MINUTE_CAPABLE_DATA_SOURCES = frozenset({"dfcf", "qq"})


class StockKlineQuerySchema(APIModel):
    """GET /api/klines 查询参数。"""

    stock_code: str = Field(min_length=1)
    market_type: str | None = None
    exchange_market: str | None = None
    stock_name: str | None = None
    data_source: DATA_SOURCE_LITERALS = "dfcf"
    kline_type: KLINE_TYPE_LITERALS = "101"
    limit: int = Field(default=2000, ge=2, le=10000)
    adjust_type: str | None = None
