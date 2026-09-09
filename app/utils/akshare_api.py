# -*- coding: utf-8 -*-
"""AKShare 日 K 数据接口。

品种 → 接口（均为日K）：
- A股：stock_zh_a_daily（新浪）
- 港股：stock_hk_daily（新浪）
- ETF/LOF 场内基金：fund_etf_hist_sina（新浪）
- 场外基金净值：fund_open_fund_info_em（天天基金）

akshare 首次 import 需数秒且接口列名随版本漂移，因此懒加载并按上述实测列名取值。
新浪系接口有频控，调用方应串行使用；本模块在请求间强制节流。
"""

import time
from typing import Any, Dict, List, Optional

from app.utils.kline_adjustment import sina_adjust
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 新浪频控安全间隔（秒）；批量任务逐参数调用本模块，宁慢勿封。
MIN_REQUEST_INTERVAL = 0.5

_last_request_time = 0.0


def _throttle() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def _call_with_retry(fn, *args, **kwargs):
    """akshare 上游偶发 JSON 解析失败/断连，小步重试两次。"""
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        _throttle()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # akshare 各接口异常类型不统一，只能宽捕获
            last_exc = exc
            if attempt < 2:
                wait = 2.0 * (attempt + 1)
                logger.warning("AKShare 请求异常 (第%d/3次): %s，%.1fs 后重试", attempt + 1, exc, wait)
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class AkshareApi:
    """AKShare 日 K 适配器，输出与 dfcf/qq 同构的标准行。"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self._ak = None

    def _get_ak(self):
        if self._ak is None:
            import akshare as ak

            self._ak = ak
        return self._ak

    def get_stock_kline_data(
        self,
        stock_code: str,
        exchange: str = "",
        limit: int = 100,
        adjust_type: str | None = None,
        market_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> List[Dict]:
        """按市场分发到对应 akshare 接口，返回按日期升序的标准 K 线行。

        stock_code 传项目统一代码（可带 .SS/.SZ/.HK 后缀）；fund 市场为 6 位基金代码。
        """
        market = str(market_type or "").strip().lower()
        code = str(stock_code or "").strip().upper().split(".")[0]
        if not code:
            raise ValueError("股票代码不能为空")

        if market == "fund":
            rows = self._fetch_fund_nav(code)
        elif market == "hk":
            rows = self._fetch_hk(code.zfill(5), adjust_type)
        elif code.startswith("5") or code[:2] in {"15", "16"}:
            # 场内基金：沪 5xxxxx / 深 15-16xxxx，走新浪基金行情接口（不复权）
            prefix = "sh" if code.startswith("5") else "sz"
            rows = self._fetch_sina_daily(self._get_ak().fund_etf_hist_sina, f"{prefix}{code}")
        else:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            rows = self._fetch_sina_daily(
                lambda symbol: self._get_ak().stock_zh_a_daily(
                    symbol=symbol, adjust=sina_adjust(adjust_type)
                ),
                f"{prefix}{code}",
            )

        rows = [
            row for row in rows
            if (not start_date or row["stock_date"] >= start_date)
            and (not end_date or row["stock_date"] <= end_date)
        ]
        if not start_date and not end_date:
            rows = rows[-max(1, int(limit or 1)):]
        self.logger.info("AKShare %s 最终返回 %d 条", code, len(rows))
        return rows

    def _fetch_sina_daily(self, fetcher, symbol: str) -> List[Dict]:
        """新浪 A股/ETF 日 K：英文列 date/open/high/low/close/volume/amount，量纲已是股/元。"""
        df = _call_with_retry(fetcher, symbol)
        rows: List[Dict] = []
        for rec in (df.to_dict("records") if df is not None else []):
            stock_date = str(rec.get("date"))[:10]
            close = rec.get("close")
            if not stock_date or close in (None, ""):
                continue
            rows.append({
                "stock_code": symbol,
                "stock_date": stock_date,
                "open": _to_float(rec.get("open")),
                "high": _to_float(rec.get("high")),
                "low": _to_float(rec.get("low")),
                "close": _to_float(close),
                "volume": _to_float(rec.get("volume")),
                "amount": _to_float(rec.get("amount")),
            })
        return rows

    def _fetch_hk(self, symbol: str, adjust_type: str | None) -> List[Dict]:
        """港股日 K 与新浪 A股同一套行映射，仅 fetcher 与 adjust 传参不同。"""
        return self._fetch_sina_daily(
            lambda sym: self._get_ak().stock_hk_daily(
                symbol=sym, adjust=sina_adjust(adjust_type)
            ),
            symbol,
        )

    def _fetch_fund_nav(self, code: str) -> List[Dict]:
        """场外基金净值序列映射为标准行：开高低=单位净值，收=累计净值（缺失回退单位净值）。"""
        ak = self._get_ak()
        dwjz = _call_with_retry(ak.fund_open_fund_info_em, symbol=code, indicator="单位净值走势")
        unit_nav = {
            str(rec.get("净值日期"))[:10]: _to_float(rec.get("单位净值"))
            for rec in (dwjz.to_dict("records") if dwjz is not None else [])
        }
        try:
            ljjz = _call_with_retry(ak.fund_open_fund_info_em, symbol=code, indicator="累计净值走势")
            acc_nav = {
                str(rec.get("净值日期"))[:10]: _to_float(rec.get("累计净值"))
                for rec in (ljjz.to_dict("records") if ljjz is not None else [])
            }
        except Exception as exc:
            self.logger.warning("AKShare 累计净值获取失败 %s，收盘回退单位净值: %s", code, exc)
            acc_nav = {}

        rows: List[Dict] = []
        for stock_date, nav in unit_nav.items():
            if not stock_date or nav <= 0:
                continue
            close = acc_nav.get(stock_date) or nav
            rows.append({
                "stock_code": code,
                "stock_date": stock_date,
                "open": nav,
                "high": max(nav, close),
                "low": min(nav, close),
                "close": close,
                "volume": 0.0,
                "amount": 0.0,
            })
        rows.sort(key=lambda row: row["stock_date"])
        return rows
