"""ETF 资产总数（totalAssets）统一取数入口。

按市场分发到各数据源适配文件，调用方只认本模块：
- 海外市场：yf_api（Yahoo totalAssets，基金计价货币原值，不做汇率归一）；
- A股：数据源暂未接入，调用位置保留于 akshare_api，当前恒 None。

取不到值（非 ETF / 数据源缺失 / 网络失败）一律返回 None，
由展示层渲染 "-"，本模块不携带展示语义。
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import get_logger
from app.utils.market import infer_market_type, normalize_market_type, to_yahoo_ticker

logger = get_logger(__name__)


def get_etf_total_assets(
    stock_code: Any,
    market_type: Any = None,
    exchange_market: Any = None,
) -> float | None:
    """按市场分发取 ETF 资产总数；任何失败路径统一返回 None。"""
    if not str(stock_code or "").strip():
        return None
    market = normalize_market_type(market_type) or infer_market_type(stock_code)
    try:
        if market == "cn":
            # A股调用位置保留：实现见 AkshareApi.get_total_assets，接入数据源前恒 None。
            from app.utils.akshare_api import AkshareApi

            return AkshareApi().get_total_assets(str(stock_code).strip(), market_type=market)
        # akshare 首次 import 需数秒，海外分支不为其付出成本；yfinance 同理按需加载。
        from app.utils.yf_api import YFApi

        ticker = to_yahoo_ticker(stock_code, market, exchange_market)
        return YFApi().get_total_assets(ticker)
    except Exception as exc:
        # 入口层兜底：provider 内部已各自降级，此处防止个别实现漏 catch 阻塞调用方。
        logger.warning("ETF 资产总数获取失败 %s: %s", stock_code, exc)
        return None
