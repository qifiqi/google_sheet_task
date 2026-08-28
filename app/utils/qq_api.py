# -*- coding: utf-8 -*-
"""腾讯财经数据接口。

使用标准 requests 访问腾讯财经 K 线接口。
接口地址: https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get
支持前复权/后复权/不复权，支持日K/周K/月K及分钟级K线。
单次最多获取 640 条，超出部分通过日期游标向前翻页获取。
"""

import logging
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter

try:
    from apis.proxy_utils import configure_session_proxy, get_proxy_for_request
except ImportError:
    # 旧版部署中的 apis 包已移除；腾讯源默认直连，保留可替换的适配函数。
    def configure_session_proxy(session):
        return session

    def get_proxy_for_request():
        return None

# ── User-Agent 池 ─────────────────────────────────────────
_USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class QQStockApi:
    """腾讯财经股票数据 API。

    - 单次请求最多 640 条，超出时自动翻页（以最早日期为游标向前取）
    - 内置重试 + 指数退避（连接断开、超时、5xx）
    - Session 连接池复用
    """

    KLINE_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"

    # 重试配置
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 1.0
    RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

    # 请求节流
    MIN_REQUEST_INTERVAL = 0.3
    MAX_REQUEST_INTERVAL = 1.0

    # 单次请求最大条数
    MAX_BATCH_SIZE = 640

    # K 线类型映射（DFCF kline_type → 腾讯 param 中的周期字段）
    KLINE_TYPE_MAP = {
        '101': 'day',
        '102': 'week',
        '103': 'month',
        '5': 'min5',
        '15': 'min15',
        '30': 'min30',
        '60': 'min60',
    }

    # 复权类型映射（统一 K 线 adjust_type → 腾讯 qfq/hfq/空）
    ADJUST_TYPE_MAP = {
        '1': 'qfq',   # 前复权
        '2': 'hfq',   # 后复权
        '0': '',       # 不复权
        'forward': 'qfq',
        'back': 'hfq',
        'none': '',
    }

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._request_count = 0
        self._last_request_time = 0.0
        self._current_ua = random.choice(_USER_AGENTS)
        self.session = self._create_session()

    # ── Session 管理 ────────────────────────────────────────

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(self._build_headers())
        session = configure_session_proxy(session)
        return session

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "User-Agent": self._current_ua if hasattr(self, '_current_ua') else random.choice(_USER_AGENTS),
            "Referer": "https://web.sqt.gtimg.cn/",
        }

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        delay = random.uniform(self.MIN_REQUEST_INTERVAL, self.MAX_REQUEST_INTERVAL)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.monotonic()

    # ── 市场前缀 ────────────────────────────────────────────

    @staticmethod
    def resolve_market_prefix(exchange: str, stock_code: str, market_type: str | None = None) -> str:
        """根据市场类型、东方财富 market 字段或股票代码推断腾讯代码前缀。

        东方财富 search 接口返回的 market 字段：
        - '0' → 深圳 (sz)
        - '1' → 上海 (sh)
        - '105' → 美股 (us)
        若 market 值不可识别，则按代码规则兜底。
        """
        normalized_market = str(market_type or '').strip().lower()
        if normalized_market in {'us', 'en', '美股', 'usa'} or str(exchange).strip() == '105':
            return 'us'
        exchange_str = str(exchange).strip()
        if exchange_str == '0':
            return 'sz'
        if exchange_str == '1':
            return 'sh'

        # 按代码规则兜底
        code = stock_code.strip()
        if code.startswith(('6', '9', '5')):
            return 'sh'
        # 0/3/1/2/4/8 开头均归深圳
        return 'sz'

    # ── 底层请求 ────────────────────────────────────────────

    def _get(self, url: str, params: Optional[Dict] = None, timeout: int = 15) -> requests.Response:
        """带重试、退避、节流的 GET 请求。"""
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            self._throttle()

            proxies = get_proxy_for_request()
            kwargs: Dict = {"timeout": timeout}
            if params:
                kwargs["params"] = params
            if proxies:
                kwargs["proxies"] = proxies

            try:
                self._request_count += 1
                response = self.session.get(url, **kwargs)
                response.raise_for_status()
                return response

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    wait = self.BACKOFF_FACTOR * (2 ** attempt) + random.uniform(0, 1)
                    self.logger.warning(
                        "腾讯K线请求异常 (第%d/%d次): %s，%.1fs 后重试",
                        attempt + 1, self.MAX_RETRIES, exc, wait,
                    )
                    time.sleep(wait)
                    continue
                self.logger.error("腾讯K线请求失败（已达最大重试次数）: %s", exc)
                raise

            except requests.HTTPError as exc:
                last_exc = exc
                if (
                    attempt < self.MAX_RETRIES
                    and exc.response is not None
                    and exc.response.status_code in self.RETRY_STATUS_CODES
                ):
                    wait = self.BACKOFF_FACTOR * (2 ** attempt) + random.uniform(0, 1)
                    self.logger.warning(
                        "腾讯K线HTTP %d (第%d/%d次)，%.1fs 后重试",
                        exc.response.status_code, attempt + 1, self.MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

        raise last_exc  # type: ignore[misc]

    # ── K 线数据 ────────────────────────────────────────────

    def get_stock_kline_data(
        self,
        stock_code: str,
        exchange: str,
        limit: int = 640,
        kline_type: str = '101',
        adjust_type: str = '1',
        market_type: str | None = None,
    ) -> List[Dict]:
        """获取股票 K 线数据，自动翻页直到收集够 limit 条或无更多历史数据。

        Args:
            stock_code:  纯数字股票代码，如 '300308'
            exchange:    东方财富 market 字段（'0'=深圳, '1'=上海, '105'=美股）
            limit:       期望获取的总条数
            kline_type:  K线周期（'101'日K / '102'周K / '103'月K / '5'/'15'/'30'/'60'分钟）
            adjust_type: 复权方式（'1'前复权 / '2'后复权 / '0'不复权）

        Returns:
            K 线记录列表，按日期升序排列
        """
        market_prefix = self.resolve_market_prefix(exchange, stock_code, market_type)
        normalized_code = str(stock_code).strip().upper()
        if market_prefix == 'us' and normalized_code.lower().startswith('us'):
            normalized_code = normalized_code[2:]
        qq_symbol = f"{market_prefix}{normalized_code}"

        qq_kline_type = self.KLINE_TYPE_MAP.get(kline_type, 'day')
        qq_adjust = self.ADJUST_TYPE_MAP.get(adjust_type, 'qfq')

        # 确定响应中的 key：qfqday / qfqweek / qfqmonth / qfqmin5 ...
        # 不复权时 key 为 day / week / month ...
        if qq_adjust:
            data_key = f"{qq_adjust}{qq_kline_type}"
        else:
            data_key = qq_kline_type

        all_records: List[Dict] = []
        cursor_date = ""  # 空字符串表示取最新数据
        remaining = limit

        while remaining > 0:
            batch_size = min(remaining, self.MAX_BATCH_SIZE)
            param = f"{qq_symbol},{qq_kline_type},{cursor_date},,{batch_size},{qq_adjust}"

            self.logger.debug("腾讯K线请求: param=%s", param)
            try:
                response = self._get(self.KLINE_URL, params={"param": param})
            except requests.RequestException:
                self.logger.exception("腾讯K线接口请求失败")
                break

            try:
                body = response.json()
            except ValueError:
                self.logger.error("腾讯K线接口返回非JSON，响应前200字: %s", response.text[:200])
                break

            # 解析响应
            data_wrapper = body.get("data", {})
            if not isinstance(data_wrapper, dict):
                self.logger.error("腾讯K线响应 data 字段异常: %s", body)
                break

            stock_data = data_wrapper.get(qq_symbol, {})
            if not isinstance(stock_data, dict):
                self.logger.error("腾讯K线响应缺少股票数据: %s", qq_symbol)
                break

            raw_klines = stock_data.get(data_key)
            if not raw_klines:
                # 可能 key 名不同，尝试遍历常见 key
                raw_klines = self._find_klines_in_dict(stock_data, data_key)
                if not raw_klines:
                    self.logger.warning("腾讯K线无数据 (key=%s)，已收集 %d 条", data_key, len(all_records))
                    break

            batch_records = []
            earliest_date = None
            for item in raw_klines:
                record = self._parse_kline_item(item, stock_code, market_type)
                if record:
                    batch_records.append(record)
                    if earliest_date is None or record['stock_date'] < earliest_date:
                        earliest_date = record['stock_date']

            if not batch_records:
                self.logger.warning("腾讯K线本批次无有效记录，停止翻页")
                break

            all_records.extend(batch_records)
            remaining -= len(batch_records)
            self.logger.info(
                "腾讯K线本批获取 %d 条，累计 %d 条，最早日期 %s",
                len(batch_records), len(all_records), earliest_date,
            )

            # 翻页：用本批最早日期作为游标继续向前取
            if not earliest_date or earliest_date == cursor_date:
                self.logger.info("腾讯K线日期游标未前进，停止翻页")
                break
            cursor_date = earliest_date

            # 如果本批不足 batch_size 条，说明已无更多历史数据
            if len(raw_klines) < batch_size:
                self.logger.info("腾讯K线本批数据不足 %d 条（实际 %d 条），已到历史尽头",
                                 batch_size, len(raw_klines))
                break

        # 去重（按日期）并按日期升序排列
        seen_dates = set()
        unique_records = []
        for r in all_records:
            d = r['stock_date']
            if d not in seen_dates:
                seen_dates.add(d)
                unique_records.append(r)
        unique_records.sort(key=lambda x: x['stock_date'])

        self.logger.info("腾讯K线最终返回 %d 条（去重后）", len(unique_records))
        return unique_records

    # ── 响应解析辅助 ────────────────────────────────────────

    @staticmethod
    def _find_klines_in_dict(stock_data: Dict, preferred_key: str) -> Optional[List]:
        """在 stock_data 中查找K线数组，优先使用 preferred_key，否则模糊匹配。"""
        # 优先精确匹配
        val = stock_data.get(preferred_key)
        if isinstance(val, list) and val:
            return val

        # 模糊匹配：找所有以 qfq/hfq/day/week/month/min 开头的 key
        for key, value in stock_data.items():
            if isinstance(value, list) and value and isinstance(value[0], list):
                return value
        return None

    @staticmethod
    def _parse_kline_item(
        item: list | Dict,
        stock_code: str,
        market_type: str | None = None,
    ) -> Optional[Dict]:
        """解析腾讯K线单条数据为标准格式。

        腾讯格式:
          [日期, 开盘, 收盘, 最高, 最低, 成交量, {分红信息}, 换手率, 成交额, ...]
        """
        try:
            if isinstance(item, dict):
                item = item.get('value')
            if not isinstance(item, list) or len(item) < 6:
                return None

            date_str = str(item[0])
            open_price = float(item[1])
            close_price = float(item[2])
            high_price = float(item[3])
            low_price = float(item[4])
            is_us_market = str(market_type or '').strip().lower() in {'us', 'en', '美股', 'usa'}
            volume = int(float(item[5]) if is_us_market else float(item[5]) * 100)

            # 换手率（索引 7，可能不存在）
            turnover_rate = 0.0
            if len(item) > 7:
                try:
                    turnover_rate = float(item[7])
                except (ValueError, TypeError):
                    turnover_rate = 0.0

            # 成交额（索引 8，可能不存在）
            # A 股接口成交额单位为万元；美股接口已是美元，不再换算。
            turnover_amount = 0.0
            if len(item) > 8:
                try:
                    turnover_amount = float(item[8]) if is_us_market else float(item[8]) * 10000.0
                except (ValueError, TypeError):
                    turnover_amount = 0.0

            # 计算涨跌额和涨跌幅（腾讯接口不直接提供，用收盘-开盘估算）
            # 注意：严格来说涨跌幅应用昨收计算，但腾讯接口不提供昨收
            # 这里先用开盘价近似（仅供展示，不影响核心OHLCV数据）
            change = round(close_price - open_price, 4)
            if open_price != 0:
                pct_change = round((change / open_price) * 100, 2)
            else:
                pct_change = 0.0

            # 振幅%
            if low_price != 0:
                amplitude = round(((high_price - low_price) / low_price) * 100, 2)
            else:
                amplitude = 0.0

            return {
                'stock_code': stock_code,
                'stock_date': date_str,
                'open': round(open_price, 2),
                'close': round(close_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'volume': volume,
                'amount': round(turnover_amount, 2),
                'amplitude': amplitude,
                'pct_change': pct_change,
                'change': round(change, 2),
                'turnover_rate': turnover_rate,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        except Exception:
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    api = QQStockApi()
    # 测试: 中际旭创 300308 深圳创业板，前复权日K，取 1280 条
    data = api.get_stock_kline_data('300308', '0', limit=1280, kline_type='101', adjust_type='1')
    print(f"获取到 {len(data)} 条K线数据")
    if data:
        print(f"最早: {data[0]['stock_date']}  最新: {data[-1]['stock_date']}")
        print("最新一条:", data[-1])
