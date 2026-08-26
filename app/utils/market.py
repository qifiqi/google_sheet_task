"""股票市场、东方财富市场编号与 Yahoo ticker 的统一映射。"""

from __future__ import annotations

from typing import Any


MARKET_LABELS = {
    "cn": "A股",
    "en": "美股",
    "ca": "加拿大",
    "kr": "韩国",
    "jp": "日本",
    "hk": "香港",
    "uk": "伦敦",
    "fr": "法国",
    "de": "德国",
    "sg": "新加坡",
    "au": "澳大利亚",
    "my": "马来西亚",
}

MARKET_DEFAULT_COMMISSIONS = {
    "cn": "0.0350%",
    "en": "0.002%",
    "ca": "0.002%",
    "kr": "0.002%",
    "jp": "0.002%",
    "hk": "0.002%",
    "uk": "0.002%",
    "fr": "0.002%",
    "de": "0.002%",
    "sg": "0.002%",
    "au": "0.002%",
    "my": "0.002%",
}

MARKET_TYPE_ALIASES = {
    "cn": "cn", "a": "cn", "a股": "cn", "ashare": "cn", "china": "cn",
    "en": "en", "us": "en", "usa": "en", "美股": "en",
    "ca": "ca", "canada": "ca", "加拿大": "ca",
    "kr": "kr", "korea": "kr", "韩国": "kr",
    "jp": "jp", "japan": "jp", "日本": "jp",
    "hk": "hk", "hongkong": "hk", "hong kong": "hk", "香港": "hk", "港股": "hk",
    "uk": "uk", "gb": "uk", "london": "uk", "伦敦": "uk", "英股": "uk",
    "fr": "fr", "france": "fr", "法国": "fr",
    "de": "de", "germany": "de", "德国": "de",
    "sg": "sg", "singapore": "sg", "新加坡": "sg",
    "au": "au", "australia": "au", "澳大利亚": "au", "澳洲": "au",
    "my": "my", "malaysia": "my", "马来西亚": "my",
}

# 东方财富搜索与 K 线接口使用的 market / secid 前缀。
EASTMONEY_MARKET_TYPES = {
    "0": "cn", "1": "cn",
    "105": "en", "106": "en", "107": "en", "153": "en",
    "116": "hk", "155": "uk", "176": "jp", "177": "kr", "185": "de", "186": "fr",
}

STOCK_CODE_SUFFIXES = {
    # 美股标准代码不使用后缀；A 股后缀由 normalize_stock_code 按交易所/代码规则处理。
    "en": "",
    "ca": ".TO",
    "kr": ".KS",
    "jp": ".T",
    "hk": ".HK",
    "uk": ".L",
    "fr": ".PA",
    "de": ".DE",
    "sg": ".SI",
    "au": ".AX",
    "my": ".KL",
}

# 历史名称兼容：后缀规则是项目统一证券代码格式，不再是 Yahoo 专属规则。
YAHOO_SUFFIXES = STOCK_CODE_SUFFIXES


def normalize_market_type(value: Any, default: str | None = None) -> str | None:
    text = str(value or "").strip().lower()
    return MARKET_TYPE_ALIASES.get(text, default)


def market_type_from_eastmoney(market: Any, security_type_name: Any = None) -> str | None:
    resolved = EASTMONEY_MARKET_TYPES.get(str(market or "").strip())
    if resolved:
        return resolved
    return normalize_market_type(security_type_name)


def normalize_stock_code(
    stock_code: Any,
    market_type: Any,
    exchange_market: Any = None,
) -> str:
    """生成项目统一证券代码格式，例如 ``600519.SS``、``0700.HK``、``AAPL``。"""
    code = str(stock_code or "").strip().upper()
    market = normalize_market_type(market_type)
    if not code or not market or market == "en":
        return code
    if "." in code:
        return f"{code[:-3]}.SS" if code.endswith(".SH") else code
    if market == "cn":
        exchange = str(exchange_market or "").strip()
        if exchange == "1" or code.startswith(("6", "68")):
            return f"{code}.SS"
        if exchange == "0" or code.startswith(("0", "2", "3")):
            return f"{code}.SZ"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return code
    if market == "hk":
        code = code.lstrip("0").zfill(4)
    suffix = STOCK_CODE_SUFFIXES.get(market)
    return f"{code}{suffix}" if suffix else code


def yahoo_symbol(stock_code: Any, market_type: Any, exchange_market: Any = None) -> str:
    """Yahoo 适配层兼容入口；统一证券代码规则由 normalize_stock_code 定义。"""
    return normalize_stock_code(stock_code, market_type, exchange_market)


def supports_internal_kline(market_type: Any) -> bool:
    return normalize_market_type(market_type) in {"cn", "en"}
