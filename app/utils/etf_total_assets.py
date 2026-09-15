"""ETF 资产总数（totalAssets）统一取数入口。

按市场分发到各数据源适配文件，调用方只认本模块：
- 海外市场：yf_api（Yahoo totalAssets，未披露时回退 marketCap 总市值，
  基金计价货币原值，不做汇率归一）；
- A股：数据源暂未接入，调用位置保留于 akshare_api，当前恒 None。

取不到值（非 ETF / 数据源缺失 / 网络失败）一律返回 None，
由展示层渲染 "-"，本模块不携带展示语义。

进程内 TTL 缓存：资产/市值日频更新，成功结果缓存 6 小时；失败（None）
短缓存 10 分钟，避免 Word 导出、预览等连续操作对同一标的反复触网。
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.utils.logger import get_logger
from app.utils.market import infer_market_type, normalize_market_type, to_yahoo_ticker

logger = get_logger(__name__)

_SUCCESS_TTL_SECONDS = 6 * 3600
_FAILURE_TTL_SECONDS = 10 * 60
# key=(代码大写, 归一市场, 交易所) → (取样时间, (资产值, 是否ETF))
_cache: dict[tuple[str, str, str], tuple[float, tuple[float | None, bool | None]]] = {}
_cache_lock = threading.Lock()


def clear_etf_total_assets_cache() -> None:
    """清空进程内缓存；测试隔离与强制刷新用。"""
    with _cache_lock:
        _cache.clear()


def get_etf_total_assets(
    stock_code: Any,
    market_type: Any = None,
    exchange_market: Any = None,
) -> float | None:
    """按市场分发取 ETF 资产总数；任何失败路径统一返回 None（带 TTL 缓存）。"""
    return get_etf_total_assets_detail(stock_code, market_type, exchange_market)[0]


def get_etf_total_assets_detail(
    stock_code: Any,
    market_type: Any = None,
    exchange_market: Any = None,
) -> tuple[float | None, bool | None]:
    """返回 (资产值, 是否 ETF)；是否 ETF 取自数据来源（totalAssets=ETF、
    marketCap 回退=个股），取不到时为 None（带 TTL 缓存）。"""
    if not str(stock_code or "").strip():
        return None, None
    market = normalize_market_type(market_type) or infer_market_type(stock_code)
    key = (str(stock_code).strip().upper(), market, str(exchange_market or "").strip())
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            stamped_at, detail = cached
            ttl = _SUCCESS_TTL_SECONDS if detail[0] is not None else _FAILURE_TTL_SECONDS
            if now - stamped_at <= ttl:
                return detail
    detail = _fetch_total_assets_detail(str(stock_code).strip(), market, exchange_market)
    with _cache_lock:
        _cache[key] = (time.monotonic(), detail)
    return detail


def _fetch_total_assets_detail(code: str, market: str, exchange_market: Any) -> tuple[float | None, bool | None]:
    try:
        if market == "cn":
            # A股调用位置保留：实现见 AkshareApi.get_total_assets，接入数据源前恒 None。
            from app.utils.akshare_api import AkshareApi

            return AkshareApi().get_total_assets(code, market_type=market), None
        # akshare 首次 import 需数秒，海外分支不为其付出成本；yfinance 同理按需加载。
        from app.utils.yf_api import YFApi

        ticker = to_yahoo_ticker(code, market, exchange_market)
        return YFApi().get_total_assets_with_source(ticker)
    except Exception as exc:
        # 入口层兜底：provider 内部已各自降级，此处防止个别实现漏 catch 阻塞调用方。
        logger.warning("ETF 资产总数获取失败 %s: %s", code, exc)
        return None, None
