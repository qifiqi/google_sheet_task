"""统一的股票 K 线数据入口。

外部数据源只在本模块装配。业务服务不再关心 DFCF、腾讯或 Yahoo 的返回格式；
内置数据库接口保留为可替换占位，接入真实数据库时只需覆盖两个方法。
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
import logging
from typing import Any, Callable, Iterable
from stock_sdk import StockClient

from app.services.stock_search_service import StockSearchService
from app.utils.dfcf_api import DFCJStockApi
from app.utils.market import normalize_market_type, supports_internal_kline, yahoo_symbol

logger = logging.getLogger(__name__)

DATA_SOURCE_DFCF = "dfcf"
DATA_SOURCE_QQ = "qq"
DATA_SOURCE_YAHOO = "yahoo"
DATA_SOURCE_TDX = "tdx"
DATA_SOURCE_DATABASE = "database"
VALID_DATA_SOURCES = {
    DATA_SOURCE_DFCF,
    DATA_SOURCE_QQ,
    DATA_SOURCE_YAHOO,
    DATA_SOURCE_TDX,
    DATA_SOURCE_DATABASE,
}


class KlineService:
    """按统一格式读取、标准化并可回填 K 线数据。"""

    def __init__(self, dfcf_api: Any | None = None, qq_api: Any | None = None, yahoo_api: Any | None = None):
        self.dfcf_api = dfcf_api or DFCJStockApi()
        self.stock_search_service = StockSearchService(dfcf_api=self.dfcf_api)
        self.stock_client = StockClient(base_url=os.environ.get("STOCK_BASE_URL", "http://172.18.20.20:8081"))
        self._qq_api = qq_api
        self.yahoo_api = yahoo_api
        self.sources: dict[str, Callable[[dict[str, Any]], Iterable[dict[str, Any]]]] = {
            DATA_SOURCE_DFCF: self._fetch_dfcf,
            DATA_SOURCE_QQ: self._fetch_qq,
            DATA_SOURCE_YAHOO: self._fetch_yahoo,
            DATA_SOURCE_TDX: self._fetch_tdx,
        }

    def register_source(
        self,
        name: str,
        handler: Callable[[dict[str, Any]], Iterable[dict[str, Any]]],
    ) -> None:
        """注册一个外部 K 线源，handler 接收标准请求字典并返回原始行。"""
        source = str(name or "").strip().lower()
        if not source or not callable(handler):
            raise ValueError("数据源名称和处理函数不能为空")
        self.sources[source] = handler

    @staticmethod
    def get_stock_market(code):
        """
        A股股票代码映射市场后缀

        Args:
            code (str or int): 6位股票代码

        Returns:
            str: 带市场后缀的代码，如 "000001.SZ"

        Examples:
            >>> get_stock_market("000001")
            '000001.SZ'
            >>> get_stock_market(600000)
            '600000.SH'
            >>> get_stock_market("688001")
            '688001.SH'
        """
        # 转为字符串并去除空格
        code = str(code).strip()

        # 如果长度不足6位，前面补0
        code = code.zfill(6)

        # 取前3位作为判断依据
        prefix = code[:3]

        # 深圳市场（主板、中小板、创业板）
        sz_prefixes = ['000', '001', '002', '003', '004', '300']
        if prefix in sz_prefixes:
            return f"{code}.SZ"

        # 上海市场（主板、科创板）
        sh_prefixes = ['600', '601', '603', '605', '688', '689']
        if prefix in sh_prefixes:
            return f"{code}.SH"

        # 北京证券交易所
        bj_prefixes = ['830', '831', '832', '833', '834', '835', '836', '837', '838', '839',
                       '870', '871', '872', '873', '874', '875', '876', '877', '878', '879',
                       '880', '881', '882', '883', '884', '885', '886', '887', '888', '889']
        if prefix in bj_prefixes:
            return f"{code}.BJ"

        # 退市股票
        if prefix in ['400', '420']:
            return f"{code}.退市"

        # B股
        if prefix == '900':
            return f"{code}.SH"  # 沪市B股
        if prefix == '200':
            return f"{code}.SZ"  # 深市B股

        # 未知代码
        return f"{code}.未知"

    def read_internal_kline_data(self, **_kwargs: Any) -> list[dict[str, Any]]:
        """读取内置 K 线库的占位接口，接入数据库时覆盖此方法。"""
        if not supports_internal_kline(_kwargs.get("market_type")):
            return []
        stock_code = _kwargs.get("stock_code")

        if str(stock_code).isdigit():
            data = self.stock_client.stock_data.get_data_all_list({
                "begin_date": _kwargs.get("start_date"),
                "stock_code": self.get_stock_market(stock_code),
            })

        else:
            data = self.stock_client.stock_data_us.get_data_all_list({
                "begin_date": _kwargs.get("start_date"),
                "stock_code": stock_code,
            })

        data = [
            {
                "stock_date": raw.get("stock_date"),
                "stock_code": raw.get("stock_code"),
                "stock_name": raw.get("stock_name"),
                "stock_kp": raw.get("stock_open"),
                "stock_zg": raw.get("stock_max"),
                "stock_zd": raw.get("stock_min"),
                "stock_sp": raw.get("stock_close"),
                "stock_cjl": raw.get("stock_volume"),
                "stock_cje": raw.get("stock_volume_price")
            } for raw in data.ret_obj
        ]

        return data

    def write_internal_kline_data(self, rows: list[dict[str, Any]], **_kwargs: Any) -> list[Any]:
        """写入内置 K 线库的占位接口，接入数据库时覆盖此方法。"""
        if not supports_internal_kline(_kwargs.get("market_type")):
            return []
        if _kwargs.get("adjust_type") != 'forward':
            return []

        stock_code = _kwargs.get("stock_code")
        if str(stock_code).isdigit(): # A 股美股不同接口
            stock_data = self.stock_client.stock_data

            stock_code = self.get_stock_market(stock_code)
        else:
            stock_data = self.stock_client.stock_data_us

        data = stock_data.get_data_all_list({
            "begin_date": rows[0]["stock_date"],
            "end_time": rows[7]["stock_date"],
            "stock_code": stock_code,
        })
        data = data.ret_obj

        if data:
            rows = sorted(rows, key=lambda x: x["stock_date"],reverse=True)[:30]

        # 创建异步任务
        async def write_one(row):
            data = {
                "stock_code": stock_code,
                "stock_name": row.get("stock_name"),
                "stock_open": row.get("stock_kp"),
                "stock_max": row.get("stock_zg"),
                "stock_min": row.get("stock_zd"),
                "stock_close": row.get("stock_sp"),
                "stock_volume": row.get("stock_cjl"),
                "stock_volume_price": row.get("stock_cje"),
                "stock_limit": row.get("stock_zdf"),
                "stock_limit_price": row.get("stock_zde"),
                "stock_date": row.get("stock_date")
            }
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, stock_data.modify_or_add, data)
            print(res, data)
            return res

        # 在 Flask 中获取当前事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果没有事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 并发执行所有任务
        tasks = [write_one(row) for row in rows]
        results = loop.run_until_complete(asyncio.gather(*tasks))
        return results


    def get_kline_data(
        self,
        stock_code: str,
        market_type: str = "cn",
        limit: int = 100,
        *,
        data_source: str = DATA_SOURCE_DFCF,
        start_date: str | None = None,
        end_date: str | None = None,
        adjust_type: str | None = None,
        exchange_market: str | None = None,
        stock_name: str | None = None,
    ) -> list[dict[str, Any]]:
        source = self.normalize_data_source(data_source, self.sources)
        code = str(stock_code or "").strip().upper()
        market_type = normalize_market_type(market_type, "cn")
        if not code:
            raise ValueError("股票代码不能为空")
        limit = max(1, int(limit or 1))

        internal_rows = []
        if source == DATA_SOURCE_DATABASE and supports_internal_kline(market_type):
            internal_rows = self._normalize_rows(
                self.read_internal_kline_data(
                    stock_code=code,
                    market_type=market_type,
                    limit=limit,
                    start_date=start_date,
                    end_date=end_date,
                    adjust_type=adjust_type,
                ),
                code,
                stock_name,
                DATA_SOURCE_DATABASE,
            )
        if self._covers_range(internal_rows, start_date, end_date, limit):
            return internal_rows[:limit]
        # database/internal 是“优先读内置库”的兼容写法；不足时仍按默认 DFCF 回退。
        if source == DATA_SOURCE_DATABASE:
            source = DATA_SOURCE_DFCF

        rows, resolved_name = self._fetch_external(
            source,
            code,
            market_type,
            limit,
            adjust_type,
            exchange_market,
            stock_name,
            start_date,
            end_date,
        )
        normalized_rows = self._normalize_rows(rows, code, resolved_name, source)
        if normalized_rows and supports_internal_kline(market_type):
            self.write_internal_kline_data(
                normalized_rows,
                stock_code=code,
                market_type=market_type,
                source=source,
                adjust_type=adjust_type,
            )
        return normalized_rows[:limit]

    @staticmethod
    def normalize_data_source(value: Any, available_sources: dict[str, Any] | None = None) -> str:
        source = str(value or DATA_SOURCE_DFCF).strip().lower()
        aliases = {"eastmoney": DATA_SOURCE_DFCF, "internal": DATA_SOURCE_DATABASE, "db": DATA_SOURCE_DATABASE}
        source = aliases.get(source, source)
        valid_sources = VALID_DATA_SOURCES | set(available_sources or {})
        if source not in valid_sources:
            raise ValueError("kline_data_source 仅支持 dfcf、qq、yahoo、tdx、database")
        return source

    def _fetch_external(
        self,
        source: str,
        code: str,
        market_type: str,
        limit: int,
        adjust_type: str | None,
        exchange_market: str | None,
        stock_name: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[Iterable[dict[str, Any]], str]:
        if source == DATA_SOURCE_TDX:
            exchange, resolved_name, resolved_code = (
                str(exchange_market or ""),
                str(stock_name or ""),
                code,
            )
        elif source == DATA_SOURCE_YAHOO:
            # Yahoo ticker 由代码和业务市场即可确定，不再调用东方财富搜索。
            exchange, resolved_name, resolved_code = (
                str(exchange_market or ""),
                str(stock_name or ""),
                code,
            )
        else:
            exchange, resolved_name, resolved_code = self._resolve_exchange_and_name(
                code, market_type, exchange_market, stock_name
            )
        handler = self.sources.get(source)
        if handler is None:
            raise ValueError(f"不支持的数据源: {source}")
        rows = handler({
            "stock_code": resolved_code,
            "market_type": market_type,
            "exchange_market": exchange,
            "limit": limit,
            "adjust_type": adjust_type,
            "start_date": start_date,
            "end_date": end_date,
            "stock_name": resolved_name,
        })
        return rows or [], resolved_name

    def _fetch_dfcf(self, request: dict[str, Any]) -> Iterable[dict[str, Any]]:
        return self.dfcf_api.get_stock_kline_data(
            request["stock_code"],
            request["exchange_market"],
            request["limit"],
            adjust_type=request.get("adjust_type"),
        )

    def _fetch_qq(self, request: dict[str, Any]) -> Iterable[dict[str, Any]]:
        return self._get_qq_api().get_stock_kline_data(
            request["stock_code"],
            request["exchange_market"],
            limit=request["limit"],
            adjust_type=request.get("adjust_type"),
            market_type=request.get("market_type"),
        )

    def _fetch_yahoo(self, request: dict[str, Any]) -> Iterable[dict[str, Any]]:
        return self._get_yahoo_api().get_kline_data(
            yahoo_symbol(
                request["stock_code"],
                request.get("market_type"),
                request.get("exchange_market"),
            ),
            "10y",
            adjust_type=request.get("adjust_type"),
        )

    def _fetch_tdx(self, request: dict[str, Any]) -> Iterable[dict[str, Any]]:
        """通过 easy-tdx 拉取 A 股日 K 线，不复用跨任务 TCP 连接。"""
        market_type = str(request.get("market_type") or "cn").strip().lower()
        if market_type not in {"cn", "a股", "china"}:
            raise ValueError("TDX 数据源仅支持 A股")

        try:
            from easy_tdx import Adjust, MacClient, Market, Period
        except ImportError as exc:
            raise RuntimeError("未安装 easy-tdx，请执行 pip install -r requirements.txt") from exc

        code = str(request["stock_code"])
        market = self._get_tdx_market(code, Market)
        adjust = {
            "forward": Adjust.QFQ,
            "back": Adjust.HFQ,
        }.get(str(request.get("adjust_type") or "none").strip().lower(), Adjust.NONE)
        with MacClient.from_best_host() as client:
            frame = client.get_stock_kline(
                market,
                code,
                Period.DAILY,
                count=request["limit"],
                adjust=adjust,
            )
            rows = frame.to_dict("records") if frame is not None else []
            if not request.get("stock_name"):
                try:
                    quotes = client.get_stock_quotes([(market, code)])
                    if quotes is not None and not quotes.empty:
                        name = str(quotes.iloc[0].get("name") or "").strip()
                        for row in rows:
                            row["stock_name"] = name
                except Exception as exc:
                    logger.warning("TDX 获取股票名称失败 code=%s: %s", code, exc)
        return rows

    @staticmethod
    def _get_tdx_market(code: str, market_enum: Any) -> Any:
        """将 A 股代码映射为 easy-tdx 市场枚举。"""
        normalized_code = str(code).strip()
        prefix = normalized_code[:1]
        if prefix == "6":
            return market_enum.SH
        if prefix in {"0", "2", "3"}:
            return market_enum.SZ
        if prefix in {"4", "8"}:
            return market_enum.BJ
        raise ValueError(f"TDX 数据源仅支持 A股股票代码: {code}")

    def _resolve_exchange_and_name(
        self,
        code: str,
        market_type: str,
        exchange_market: str | None,
        stock_name: str | None,
    ) -> tuple[str, str, str]:
        resolved = self.stock_search_service.resolve_stock(code, market_type)
        selected_exchange_market = str(exchange_market or "").strip()
        if selected_exchange_market and selected_exchange_market != resolved["exchange_market"]:
            logger.warning(
                "任务传入交易市场与查询结果不一致 code=%s provided=%s resolved=%s",
                code,
                selected_exchange_market,
                resolved["exchange_market"],
            )
        return (
            resolved["exchange_market"],
            str(stock_name or resolved["name"]),
            resolved["code"],
        )

    def _get_qq_api(self) -> Any:
        if self._qq_api is None:
            from app.utils.qq_api import QQStockApi

            self._qq_api = QQStockApi()
        return self._qq_api

    def _get_yahoo_api(self) -> Any:
        if self.yahoo_api is None:
            from app.utils.yf_api import YFApi

            self.yahoo_api = YFApi()
        return self.yahoo_api

    @staticmethod
    def _covers_range(
        rows: list[dict[str, Any]],
        start_date: str | None,
        end_date: str | None,
        limit: int,
    ) -> bool:
        if not rows:
            return False
        dates = [str(row.get("stock_date") or "")[:10] for row in rows]
        dates = [date for date in dates if date]
        if not dates:
            return False
        if not start_date and not end_date:
            return len(rows) >= limit
        return (not start_date or min(dates) <= str(start_date)[:10]) and (
            not end_date or max(dates) >= str(end_date)[:10]
        )

    @staticmethod
    def _normalize_rows(
        rows: Iterable[dict[str, Any]] | None,
        stock_code: str,
        stock_name: str | None,
        source: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in rows or []:
            if not isinstance(raw, dict):
                continue
            date = raw.get("stock_date") or raw.get("date") or raw.get("trade_date") or raw.get("datetime")
            if not date:
                continue
            open_value = raw.get("stock_kp", raw.get("open"))
            close_value = raw.get("stock_sp", raw.get("close"))
            high_value = raw.get("stock_zg", raw.get("high"))
            low_value = raw.get("stock_zd", raw.get("low"))
            # 兼容旧的测试/数据库记录：只有开收盘时用两者推导高低价。
            if high_value in (None, "") and open_value not in (None, "") and close_value not in (None, ""):
                high_value = max(float(open_value), float(close_value))
            if low_value in (None, "") and open_value not in (None, "") and close_value not in (None, ""):
                low_value = min(float(open_value), float(close_value))
            values = {
                "stock_kp": open_value,
                "stock_sp": close_value,
                "stock_zg": high_value,
                "stock_zd": low_value,
            }
            try:
                values = {key: float(value) for key, value in values.items()}
            except (TypeError, ValueError):
                continue
            code = str(raw.get("stock_code") or raw.get("code") or stock_code).strip().upper()
            name = str(raw.get("stock_name") or raw.get("name") or stock_name or "").strip()
            row = dict(raw)
            volume = raw.get("stock_cjl", raw.get("volume", raw.get("vol", 0))) or 0
            try:
                volume = float(volume)
            except (TypeError, ValueError):
                volume = 0.0
            stock_cje = raw.get("stock_cje", raw.get("amount", 0)) or 0
            try:
                stock_cje = float(stock_cje)
            except (TypeError, ValueError):
                stock_cje = 0.0
            stock_vwap_raw = raw.get("stock_vwap")
            try:
                stock_vwap = float(stock_vwap_raw) if stock_vwap_raw not in (None, "") else (
                    stock_cje / volume if volume else values["stock_sp"]
                )
            except (TypeError, ValueError):
                stock_vwap = values["stock_sp"]
            row.update(
                {
                    **values,
                    "stock_code": code,
                    "stock_name": name,
                    "stock_date": str(date)[:10],
                    "open": values["stock_kp"],
                    "close": values["stock_sp"],
                    "high": values["stock_zg"],
                    "low": values["stock_zd"],
                    "stock_cjl": volume,
                    "stock_cje": stock_cje,
                    "stock_vwap": stock_vwap,
                    "data_source": source,
                    "timestamp": raw.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            normalized.append(row)
        normalized.sort(key=lambda row: row["stock_date"])
        return normalized
