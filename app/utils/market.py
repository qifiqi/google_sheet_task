"""股票市场、东方财富市场编号与 Yahoo ticker 的统一映射。"""

from __future__ import annotations

import re
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

# A 股场内品种（股票/ETF/LOF/可转债等）在东方财富接口中的 market 数字：
# 沪市 = "1"，深市 = "0"。数字落在该集合内一律归为 A 股（cn），
# 避免 ETF/基金/场内品种因 securityTypeName 缺少市场信息而被判为未知。
CN_EASTMONEY_MARKETS = {"0", "1"}


def resolve_market_type(market_number: Any, security_type_name: Any = None) -> str | None:
    """统一市场判定接口：按东方财富 market 数字范围判断。

    判定顺序：
    1. 已知市场映射表（美股/港股/日韩等按编号对应）；
    2. A 股场内数字范围（沪 1 / 深 0，覆盖股票、ETF、LOF 等场内品种）→ cn；
    3. securityTypeName 别名兜底；仍无法判定返回 None。
    """
    number = str(market_number or "").strip()
    if number:
        resolved = EASTMONEY_MARKET_TYPES.get(number)
        if resolved:
            return resolved
        if number in CN_EASTMONEY_MARKETS:
            return "cn"
    return normalize_market_type(security_type_name)

STOCK_CODE_SUFFIXES = {
    # A 股后缀由 normalize_stock_code 按交易所/代码规则处理。
    "en": ".US",
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

STANDARD_SUFFIX_MARKETS = {
    ".SS": "cn", ".SH": "cn", ".SZ": "cn", ".BJ": "cn",
    **{suffix.upper(): market for market, suffix in STOCK_CODE_SUFFIXES.items()},
}

# 历史名称兼容：后缀规则是项目统一证券代码格式，不再是 Yahoo 专属规则。
YAHOO_SUFFIXES = STOCK_CODE_SUFFIXES


def normalize_market_type(value: Any, default: str | None = None) -> str | None:
    text = str(value or "").strip().lower()
    return MARKET_TYPE_ALIASES.get(text, default)


def market_type_from_eastmoney(market: Any, security_type_name: Any = None) -> str | None:
    """兼容入口：统一走 resolve_market_type 判定。"""
    return resolve_market_type(market, security_type_name)


def split_stock_code(stock_code: Any) -> tuple[str, str | None]:
    """拆分项目标准代码，返回无后缀代码与标准后缀。"""
    code = str(stock_code or "").strip().upper()
    if "." not in code:
        return code, None
    base, suffix = code.rsplit(".", 1)
    suffix = f".{suffix}"
    return (base, suffix) if suffix in STANDARD_SUFFIX_MARKETS else (code, None)


def infer_market_type(stock_code: Any, default: Any = None) -> str | None:
    """从标准代码后缀推断市场；没有后缀时使用默认值或代码形态。"""
    _base, suffix = split_stock_code(stock_code)
    if suffix:
        return STANDARD_SUFFIX_MARKETS[suffix]
    return normalize_market_type(default) or (
        "cn" if str(stock_code or "").strip().isdigit() else "en"
    )


def strip_stock_code_suffix(stock_code: Any) -> str:
    """还原为外部数据源常用的无后缀代码。"""
    return split_stock_code(stock_code)[0]


def exchange_market_from_stock_code(stock_code: Any, default: Any = None) -> str:
    """从统一代码推导东方财富/交易所市场编号。"""
    _base, suffix = split_stock_code(stock_code)
    if suffix == ".SS" or suffix == ".SH":
        return "1"
    if suffix in {".SZ", ".BJ"}:
        return "0"
    return str(default or "").strip()


def normalize_stock_code(
    stock_code: Any,
    market_type: Any,
    exchange_market: Any = None,
) -> str:
    """生成项目统一证券代码格式，例如 ``600519.SS``、``0700.HK``、``AAPL.US``。"""
    original_code = str(stock_code or "").strip().upper()
    code, existing_suffix = split_stock_code(original_code)
    market = infer_market_type(stock_code, market_type)
    if not code or not market:
        return code
    # 旧任务可能只留下中文名称而没有 stock_code；不能伪造成 "名称.US"。
    # 正常证券代码仅在无后缀时由字母、数字和连字符组成。
    if code == "UNKNOWN" or not re.fullmatch(r"[A-Z0-9-]+", code):
        return original_code
    # 保留数据源已给出的、当前映射表外的有效交易所后缀（如韩国 KOSDAQ 的 .KQ）。
    if "." in original_code and existing_suffix is None:
        return original_code
    if market == "cn":
        exchange = str(exchange_market or "").strip()
        if existing_suffix in {".SS", ".SH"}:
            return f"{code}.SS"
        if existing_suffix in {".SZ", ".BJ"}:
            return f"{code}{existing_suffix}"
        # 沪市：6(股票/科创板)、5(基金/ETF，如 510300)
        if exchange == "1" or code.startswith(("5", "6")):
            return f"{code}.SS"
        # 深市：0(主板)、1(基金/ETF/债券)、2(B股)、3(创业板，如 159919)
        if exchange == "0" or code.startswith(("0", "1", "2", "3")):
            return f"{code}.SZ"
        # 北交所：4/8 开头
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return code
    if market == "hk":
        code = code.lstrip("0").zfill(4)
    suffix = STOCK_CODE_SUFFIXES.get(market)
    return f"{code}{suffix}" if suffix else code


def to_yahoo_ticker(stock_code: Any, market_type: Any, exchange_market: Any = None) -> str:
    """将项目标准证券代码转换为 Yahoo 所需 ticker；美股不带 ``.US`` 后缀。"""
    code = normalize_stock_code(stock_code, market_type, exchange_market)
    if infer_market_type(code, market_type) == "en" and code.endswith(".US"):
        return code[:-3]
    return code


def yahoo_symbol(stock_code: Any, market_type: Any, exchange_market: Any = None) -> str:
    """Yahoo 适配层兼容入口。"""
    return to_yahoo_ticker(stock_code, market_type, exchange_market)


def supports_internal_kline(market_type: Any) -> bool:
    return normalize_market_type(market_type) in {"cn", "en"}
