"""腾讯财经行情适配：symbol 映射、GBK 解析、亿元换算与契约护栏。"""

import pytest

from app.utils.tencent_api import TencentStockApi


class _FakeResponse:
    status_code = 200

    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def _quote_fields(code, cap="9.23", type_mark="ETF"):
    """按字段契约构造最小快照：2 代码、3 现价、44/45 市值（亿）、61 类型。"""
    fields = [""] * 62
    fields[0:3] = ["51", "测试标的", code]
    fields[3] = "1.737"
    fields[44:46] = [cap, cap]
    fields[61] = type_mark
    return fields


def _api_capturing(monkeypatch, content=None, exc=None):
    """替身 session.get，记录请求 URL 并返回预设内容/异常。"""
    api = TencentStockApi()
    captured = {"urls": []}

    def _fake_get(url, **kwargs):
        captured["urls"].append(url)
        if exc is not None:
            raise exc
        return _FakeResponse(content)

    monkeypatch.setattr(api.session, "get", _fake_get)
    return api, captured


def _quote_body(fields):
    return ('v_sz159930="' + "~".join(fields) + '";').encode("gbk")


def test_parses_total_market_cap_and_marks_fund(monkeypatch):
    """字段 45 亿元→元换算；场内基金按代码前缀标记 ETF。"""
    api, captured = _api_capturing(monkeypatch, _quote_body(_quote_fields("159930", cap="9.23")))
    assert api.get_total_assets_with_source("159930") == (pytest.approx(9.23e8), True)
    assert captured["urls"] == ["https://qt.gtimg.cn/q=sz159930"]


def test_stock_market_cap_and_suffix_strip(monkeypatch):
    """个股标记非 ETF；.SH/.sz 后缀剥离后仍按代码回读校验。"""
    api, captured = _api_capturing(
        monkeypatch, _quote_body(_quote_fields("600519", cap="16057.30", type_mark="GP-A"))
    )
    assert api.get_total_assets_with_source("600519.SH") == (pytest.approx(1.605730e12), False)
    assert captured["urls"] == ["https://qt.gtimg.cn/q=sh600519"]

    captured["urls"].clear()
    api, captured = _api_capturing(
        monkeypatch, _quote_body(_quote_fields("159915", cap="65.81", type_mark="ETF"))
    )
    assert api.get_total_assets_with_source("159915.sz") == (pytest.approx(6.581e9), True)
    assert captured["urls"] == ["https://qt.gtimg.cn/q=sz159915"]


def test_symbol_mapping_covers_all_boards():
    """沪 5/6/9（含 900 沪B）、北交 4/8/920，其余归深。"""
    to_symbol = TencentStockApi._to_tencent_symbol
    assert to_symbol("159930") == "sz159930"
    assert to_symbol("000001") == "sz000001"
    assert to_symbol("300750") == "sz300750"
    assert to_symbol("510300") == "sh510300"
    assert to_symbol("600519") == "sh600519"
    assert to_symbol("688981") == "sh688981"
    assert to_symbol("900901") == "sh900901"
    assert to_symbol("832566") == "bj832566"
    assert to_symbol("430047") == "bj430047"
    assert to_symbol("920099") == "bj920099"


def test_mismatched_code_fails_contract(monkeypatch):
    """响应代码与请求不符（字段错位/串行）视为契约失败，交由上层兜底。"""
    api, _ = _api_capturing(monkeypatch, _quote_body(_quote_fields("000001", cap="2280.20")))
    assert api.get_total_assets_with_source("159930") == (None, None)


def test_unknown_code_none_match_degrades(monkeypatch):
    """未知代码返回 v_pv_none_match="1"，字段不足按契约失败降级。"""
    api, _ = _api_capturing(monkeypatch, 'v_pv_none_match="1";'.encode("gbk"))
    assert api.get_total_assets_with_source("999999") == (None, None)


def test_invalid_market_cap_degrades(monkeypatch):
    """停牌/未披露（"-"）、零值与空响应一律 (None, None)。"""
    api, _ = _api_capturing(monkeypatch, _quote_body(_quote_fields("600519", cap="-", type_mark="GP-A")))
    assert api.get_total_assets_with_source("600519") == (None, None)

    api, _ = _api_capturing(monkeypatch, _quote_body(_quote_fields("600519", cap="0.00", type_mark="GP-A")))
    assert api.get_total_assets_with_source("600519") == (None, None)

    api, _ = _api_capturing(monkeypatch, b"")
    assert api.get_total_assets_with_source("600519") == (None, None)


def test_network_error_degrades(monkeypatch):
    """请求异常不外抛，返回 (None, None) 由上层东财兜底。"""
    api, captured = _api_capturing(monkeypatch, exc=RuntimeError("network"))
    assert api.get_total_assets_with_source("159930") == (None, None)
    assert len(captured["urls"]) == 1


def test_non_digit_code_skips_request(monkeypatch):
    """非数字代码不触发请求。"""
    api, captured = _api_capturing(monkeypatch, b"")
    assert api.get_total_assets_with_source("BTC") == (None, None)
    assert captured["urls"] == []
