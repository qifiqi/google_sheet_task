"""腾讯财经公开行情适配（qt.gtimg.cn 文本行情快照）。

etf_total_assets 的 A股主数据源：单行 GBK 文本、~ 分隔字段的公开行情，
无 WAF/令牌，直连可用；字段为位置定位（非命名 JSON），以代码回读校验
（字段 2 == 请求代码）作错位护栏，解析不符合契约一律返回 (None, None)，
由 etf_total_assets 层降级到东方财富 dfcf_api。

字段契约（实测 2026-10-12，总市值与 DFCJStockApi 的 f116 同口径）：
- 字段 2 代码、3 最新价、44 流通市值（亿）、45 总市值（亿）、61 类型标记
  （GP-A / GP-A-KCB / GP / ETF / LOF）；
- 场内基金（ETF/LOF）总市值 = 最新价×总份额（基金规模量级），个股即
  总市值；单位亿元，×1e8 转元，不做汇率归一。
"""

from __future__ import annotations

import requests

from app.utils.logger import get_logger
from app.utils.market import strip_stock_code_suffix

_QUOTE_URL = "https://qt.gtimg.cn/q="
# 位置字段下标：代码回读校验与总市值（亿元）。
_CODE_INDEX = 2
_TOTAL_MARKET_CAP_INDEX = 45


class TencentStockApi:
    """腾讯财经行情：etf_total_assets 的 A股总市值主源（东方财富兜底）。"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Referer": "https://gu.qq.com/",
            }
        )

    def get_total_assets_with_source(self, stock_code):
        """返回 (总市值元, 是否 ETF)；解析失败/契约不符/网络异常一律 (None, None)。"""
        code = strip_stock_code_suffix(str(stock_code or "").strip().upper())
        if not code.isdigit():
            return None, None
        try:
            response = self.session.get(_QUOTE_URL + self._to_tencent_symbol(code), timeout=10)
            response.raise_for_status()
            # 未知代码返回 v_pv_none_match="1"；字段错位时代码回读不符；
            # 两者一并按契约失败降级，交由上层东财兜底。
            fields = response.content.decode("gbk", errors="replace").split("=", 1)[-1]
            fields = fields.strip().strip(";").strip('"').split("~")
            if len(fields) <= _TOTAL_MARKET_CAP_INDEX or fields[_CODE_INDEX] != code:
                self.logger.warning("腾讯财经行情契约不符: code=%s head=%s", code, fields[:5])
                return None, None
            cap_yi = float(fields[_TOTAL_MARKET_CAP_INDEX])
            if cap_yi <= 0:
                # 停牌/未披露时可能为 0 或负值，总市值不可能非正。
                self.logger.warning("腾讯财经行情无有效总市值: code=%s cap_yi=%s", code, cap_yi)
                return None, None
            return cap_yi * 1e8, self._is_a_share_fund(code)
        except Exception as exc:
            self.logger.warning("腾讯财经 A股总市值获取失败 %s: %s", code, exc)
            return None, None

    @staticmethod
    def _to_tencent_symbol(code) -> str:
        """A股代码 → 腾讯 symbol：沪 5/6/9（含 900 沪B）、北交 4/8/920，其余深。"""
        code = str(code)
        if code.startswith(("4", "8")) or code.startswith("920"):
            return "bj" + code
        if code.startswith(("5", "6", "9")):
            return "sh" + code
        return "sz" + code

    @staticmethod
    def _is_a_share_fund(code) -> bool:
        """场内基金（ETF/LOF）判定，与 DFCJStockApi._is_a_share_fund 同规则：
        沪 5xxxxx / 深 15-16xxxx（AKShare K线路径同规则）。"""
        code = str(code)
        return code.startswith("5") or code[:2] in {"15", "16"}
