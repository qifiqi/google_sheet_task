import hashlib
import json
import os
import random
import time
from urllib.parse import quote

import requests
from requests.exceptions import RequestException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.services.config_manager import get_config_manager
from app.utils.kline_adjustment import eastmoney_fqt
from app.utils.logger import get_logger
from app.utils.proxy_manager import SmartProxyManager, get_smart_proxy_manager
from app.utils.task_error_utils import is_retryable_network_error

os.environ["REQUESTS_CA_BUNDLE"] = requests.utils.DEFAULT_CA_BUNDLE_PATH

logger = get_logger(__name__)


class DFCJStockApi:
    """
    东方财富网数据接口。
    """

    def __init__(self):
        self.ut_fixed = None
        self.logger = get_logger(self.__class__.__name__)
        self.proxy_manager = get_smart_proxy_manager(self.logger)
        self._reset_session()

    def _reset_session(self):
        if getattr(self, "session", None) is not None:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.verify = requests.utils.DEFAULT_CA_BUNDLE_PATH
        self.session.headers.update(self._generate_headers())

    def _refresh_proxy_after_failure(self, exc):
        self._reset_session()
        self.proxy_manager.invalidate_proxy()
        try:
            self.proxy_manager.get_best_proxy(force_refresh=True)
        except Exception as refresh_exc:
            self.logger.warning("DFCF代理刷新失败: %s", refresh_exc)
        self.logger.warning("DFCF代理请求失败，已重建会话并尝试刷新代理: %s", exc)

    def _generate_headers(self, referer=None):
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _should_use_proxy_for_kline(self):
        raw_value = get_config_manager().get_config("dfcf_kline_proxy_enabled", "false")
        if isinstance(raw_value, bool):
            return raw_value
        return str(raw_value).strip().lower() in ("1", "true", "yes", "on")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def __get(self, *args, **kwargs):
        use_proxy = bool(kwargs.pop("use_proxy", False))
        headers = kwargs.pop("headers", None)
        if headers is None:
            headers = self._generate_headers()

        try:
            if use_proxy:
                proxy = self.proxy_manager.get_best_proxy()
                self.logger.info(
                    "DFCF K线请求启用代理: %s",
                    SmartProxyManager._redact_proxy(proxy),
                )
                response = self.session.get(*args, **kwargs, headers=headers, proxies=proxy)
            else:
                response = self.session.get(*args, **kwargs, headers=headers)
        except RequestException as exc:
            if use_proxy:
                self._refresh_proxy_after_failure(exc)
            else:
                self._reset_session()
                self.logger.warning("DFCF请求失败，已重建会话: %s", exc)
            raise

        response.raise_for_status()
        return response

    def get_stock_kline_data(self, stock_code, stock_type, limit=100, kline_type="101", adjust_type=None):
        try:
            url = self._build_eastmoney_url(stock_type, stock_code, limit, kline_type, adjust_type)
            if not url:
                self.logger.error("无法构建东方财富API URL，参数可能不正确")
                return []

            self.logger.debug(f"请求东方财富K线接口: {url}")
            response = self.__get(url, timeout=10, use_proxy=self._should_use_proxy_for_kline())
            if response.status_code != 200:
                self.logger.error(f"请求失败: {response.status_code}")
                return []

            data = response.json()
            if "data" not in data or "klines" not in data["data"]:
                self.logger.error(f"数据格式错误: {data}")
                return []

            kline_data = []
            for line in data["data"]["klines"]:
                kline = self._parse_kline_data(line, data["data"]["code"])
                if kline:
                    kline_data.append(kline)

            self.logger.info(f"获取K线数据成功，记录数: {len(kline_data)} code={stock_code}")
            return kline_data
        except Exception:
            raise

    def generate_wbp2u(self):
        timestamp = int(time.time() * 1000) * 1000 + random.randint(0, 9999)
        return f"{timestamp}|0|1|0|web"

    def get_ut(self, use_random=False):
        if use_random:
            raw_string = f"{time.time()}{random.random()}"
            return hashlib.md5(raw_string.encode()).hexdigest()
        return self.ut_fixed

    def _build_eastmoney_url(self, stock_type, stock_code, limit, kline_type="101", adjust_type=None):
        base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        ut = self.get_ut(True)
        secid = f"{stock_type}.{stock_code}"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": ut,
            "secid": secid,
            "dect": "1",
            "klt": kline_type,
            "lmt": str(limit),
            "fqt": eastmoney_fqt(adjust_type),
            "forcect": "1",
            "end": "20500000",
            "wbp2u": self.generate_wbp2u(),
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        built = f"{base_url}?{query_string}"
        self.logger.debug(f"构建的URL: {built}")
        return built

    def _parse_kline_data(self, line, stock_code):
        try:
            data = line.split(",")
            if len(data) < 10:
                logger.warning(f"K线原始数据字段数量不足: {line}")
                return None
            return {
                "stock_code": stock_code,
                "stock_date": data[0],
                "stock_kp": float(data[1]),
                "stock_sp": float(data[2]),
            }
        except Exception:
            logger.exception("解析K线数据失败")
            return None

    def get_search_list_by_stock_code(self, stock, page_size=20):
        normalized_page_size = max(1, min(int(page_size or 20), 20))

        rows = self._search_codetable(stock, normalized_page_size)
        if isinstance(rows, list) and rows:
            return rows

        fallback_rows = self._search_suggest(stock, normalized_page_size)
        if isinstance(fallback_rows, list):
            return fallback_rows
        return fallback_rows

    def _search_codetable(self, stock, page_size):
        try:
            url = "https://search-codetable.eastmoney.com/codetable/search/web"
            params = {
                "client": "web",
                "clientType": "webSuggest",
                "clientVersion": "lastest",
                "cb": f"jQuery{random.randint(10**15, 10**16 - 1)}_{int(time.time() * 1000)}",
                "keyword": stock,
                "pageIndex": 1,
                "pageSize": page_size,
                "securityFilter": "",
                "_": str(int(time.time() * 1000)),
            }
            headers = self._generate_headers(referer=f"https://so.eastmoney.com/web/s?keyword={quote(stock)}")
            self.logger.debug(f"请求东方财富搜索接口（codetable）: {url} params={params}")
            response = self.__get(url, headers=headers, params=params, timeout=10)
            json_str = response.text
            if "(" in json_str and ")" in json_str:
                json_str = json_str[json_str.find("(") + 1:json_str.rfind(")")]
            json_data = json.loads(json_str)
            self.logger.debug(f"接口url:{response.url}\n 搜索接口返回数据: {json_data}")

            rows = json_data.get("result") or []
            if not isinstance(rows, list):
                self.logger.error(f"搜索接口返回数据格式不正确: {json_data}")
                return {"error": "数据格式错误"}

            normalized_rows = []
            keyword_upper = str(stock or "").strip().upper()
            for item in rows[:page_size]:
                code = str(item.get("code") or "").strip().upper()
                if not code:
                    continue

                market_value = item.get("market")
                market = "" if market_value is None else str(market_value).strip()
                normalized_rows.append({
                    "source": "codetable",
                    "code": code,
                    "shortName": str(item.get("shortName") or "").strip(),
                    "securityTypeName": str(item.get("securityTypeName") or "").strip(),
                    "market": market,
                    "status": item.get("status", 10),
                    "isExactMatch": code == keyword_upper,
                    "innerCode": str(item.get("innerCode") or "").strip(),
                    "pinyin": str(item.get("pinyin") or "").strip(),
                    "securityType": item.get("securityType"),
                    "smallType": item.get("smallType"),
                    "flag": item.get("flag"),
                    "extSmallType": item.get("extSmallType"),
                })

            return normalized_rows

        except json.JSONDecodeError as je:
            self.logger.warning(f"codetable 搜索 JSON 解析失败: {je}")
            return []
        except Exception as e:
            if is_retryable_network_error(e):
                raise
            self.logger.warning(f"codetable 搜索失败: {e}")
            return []

    def _search_suggest(self, stock, page_size):
        try:
            url = "https://searchapi.eastmoney.com/api/suggest/get"
            params = {
                "input": stock,
                "type": 14,
                "count": page_size,
            }
            headers = self._generate_headers(referer=f"https://so.eastmoney.com/web/s?keyword={quote(stock)}")
            self.logger.debug(f"请求东方财富搜索接口（suggest）: {url} params={params}")
            response = self.__get(url, headers=headers, params=params, timeout=10)
            json_data = response.json()
            self.logger.debug(f"接口url:{response.url}\n suggest 搜索接口返回数据: {json_data}")

            quotation_table = json_data.get("QuotationCodeTable") or {}
            rows = quotation_table.get("Data") or []
            if not isinstance(rows, list):
                self.logger.error(f"suggest 搜索接口返回数据格式不正确: {json_data}")
                return {"error": "数据格式错误"}

            normalized_rows = []
            keyword_upper = str(stock or "").strip().upper()
            for item in rows[:page_size]:
                code = str(item.get("Code") or "").strip().upper()
                if not code:
                    continue

                quote_id = str(item.get("QuoteID") or "").strip()
                market = quote_id.split(".", 1)[0] if "." in quote_id else str(item.get("MktNum") or item.get("MarketType") or "").strip()
                normalized_rows.append({
                    "source": "suggest",
                    "code": code,
                    "shortName": str(item.get("Name") or "").strip(),
                    "securityTypeName": str(item.get("SecurityTypeName") or "").strip(),
                    "market": market,
                    "status": 10,
                    "isExactMatch": code == keyword_upper,
                    "innerCode": str(item.get("InnerCode") or "").strip(),
                    "pinyin": str(item.get("PinYin") or "").strip(),
                    "securityType": item.get("SecurityType"),
                    "smallType": item.get("TypeUS"),
                    "flag": None,
                    "extSmallType": None,
                    "quoteId": quote_id,
                    "marketType": item.get("MarketType"),
                    "unifiedCode": str(item.get("UnifiedCode") or "").strip(),
                    "jys": str(item.get("JYS") or "").strip(),
                    "classify": str(item.get("Classify") or "").strip(),
                })

            return normalized_rows

        except json.JSONDecodeError as je:
            self.logger.exception("suggest 搜索接口返回数据无法解析为JSON")
            return {"error": f"JSON解析失败: {str(je)}"}
        except Exception as e:
            if is_retryable_network_error(e):
                raise
            self.logger.exception("suggest 搜索接口调用失败")
            return {"error": f"未知错误: {str(e)}"}


if __name__ == "__main__":
    api = DFCJStockApi()
    print(api.get_search_list_by_stock_code("000001", 10))
