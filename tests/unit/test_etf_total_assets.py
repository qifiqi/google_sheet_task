"""ETF 资产总数统一入口：市场分发、代码转换、TTL 缓存与降级行为。"""

import pytest

from app.utils import akshare_api, yf_api
from app.utils.etf_total_assets import (
    clear_etf_total_assets_cache,
    get_etf_total_assets,
    get_etf_total_assets_detail,
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    """同一代码在成功/失败用例间复用，先清缓存避免命中上一用例的 TTL 结果。"""
    clear_etf_total_assets_cache()
    yield
    clear_etf_total_assets_cache()


class _FakeYFApi:
    """记录调用并按预设返回/抛错的雅虎替身。"""

    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc
        self.calls = []

    def get_total_assets_with_source(self, ticker):
        self.calls.append(ticker)
        if self.exc is not None:
            raise self.exc
        if self.value is None:
            return None, None
        return self.value, True

    def get_total_assets(self, ticker):
        return self.get_total_assets_with_source(ticker)[0]


def test_overseas_dispatches_to_yahoo_and_converts_ticker(monkeypatch):
    fake = _FakeYFApi(value=353240930304.0)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("QQQ.US", "en") == 353240930304.0
    assert get_etf_total_assets_detail("QQQ.US", "en") == (353240930304.0, True)
    assert fake.calls == ["QQQ"]


def test_detail_marks_total_assets_as_etf_and_market_cap_as_stock(monkeypatch):
    """totalAssets 命中视为 ETF；marketCap 回退视为个股；都缺失为 (None, None)。"""

    class _SourceAwareYFApi:
        def __init__(self, info):
            self.info = info

        def get_total_assets_with_source(self, ticker):
            if self.info.get("totalAssets") is not None:
                return float(self.info["totalAssets"]), True
            if self.info.get("marketCap") is not None:
                return float(self.info["marketCap"]), False
            return None, None

    info = {"totalAssets": 353240930304}
    monkeypatch.setattr(yf_api, "YFApi", lambda: _SourceAwareYFApi(info))
    assert get_etf_total_assets_detail("QQQ.US", "en") == (353240930304.0, True)

    clear_etf_total_assets_cache()
    info.clear()
    info.update({"marketCap": 4861029515264})
    assert get_etf_total_assets_detail("QQQ.US", "en") == (4861029515264.0, False)

    clear_etf_total_assets_cache()
    info.clear()
    assert get_etf_total_assets_detail("QQQ.US", "en") == (None, None)


def test_overseas_market_type_alias_and_hk_ticker(monkeypatch):
    fake = _FakeYFApi(value=None)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("0700.HK", "美股") is None  # 非 ETF：None 原样透传
    assert fake.calls == ["0700.HK"]


def test_overseas_yahoo_failure_degrades_to_none(monkeypatch):
    fake = _FakeYFApi(exc=RuntimeError("network"))
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("QQQ.US", "en") is None
    assert fake.calls == ["QQQ"]
    # 失败结果短缓存：TTL 内重复调用不触网。
    assert get_etf_total_assets("QQQ.US", "en") is None
    assert fake.calls == ["QQQ"]


def test_success_result_hits_ttl_cache(monkeypatch):
    fake = _FakeYFApi(value=353240930304.0)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("QQQ.US", "en") == 353240930304.0
    assert get_etf_total_assets("QQQ.US", "en") == 353240930304.0
    assert fake.calls == ["QQQ"]
    clear_etf_total_assets_cache()
    assert get_etf_total_assets("QQQ.US", "en") == 353240930304.0
    assert fake.calls == ["QQQ", "QQQ"]


def test_empty_code_returns_none_without_dispatch(monkeypatch):
    fake = _FakeYFApi(value=1.0)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("   ", "en") is None
    assert fake.calls == []


def test_cn_branch_hits_akshare_reserved_stub():
    # A股保留调用位：真实 AkshareApi 恒 None 且不触网；无 market_type 的纯数字代码同样路由到 cn。
    assert get_etf_total_assets("510300.SH", "cn") is None
    assert get_etf_total_assets("510300") is None


def test_yf_total_assets_parses_and_falls_back_to_market_cap(monkeypatch):
    api = yf_api.YFApi()

    monkeypatch.setattr(
        yf_api.yf, "Ticker", lambda symbol: type("T", (), {"info": {"totalAssets": "353240930304"}})()
    )
    assert api.get_total_assets("QQQ") == 353240930304.0
    assert api.get_total_assets_with_source("QQQ") == (353240930304.0, True)

    # 非 ETF 未披露 totalAssets 时回退 marketCap（总市值），并标记为非 ETF。
    monkeypatch.setattr(
        yf_api.yf, "Ticker", lambda symbol: type("T", (), {"info": {"marketCap": 4861029515264}})()
    )
    assert api.get_total_assets("AAPL") == 4861029515264.0
    assert api.get_total_assets_with_source("AAPL") == (4861029515264.0, False)

    # 两者都缺失才降级 None。
    monkeypatch.setattr(yf_api.yf, "Ticker", lambda symbol: type("T", (), {"info": {}})())
    assert api.get_total_assets("AAPL") is None
    assert api.get_total_assets_with_source("AAPL") == (None, None)

    def _boom(symbol):
        raise RuntimeError("network")

    monkeypatch.setattr(yf_api.yf, "Ticker", _boom)
    assert api.get_total_assets("QQQ") is None
    assert api.get_total_assets_with_source("QQQ") == (None, None)


def test_akshare_total_assets_reserved_stub_returns_none():
    assert akshare_api.AkshareApi().get_total_assets("510300.SH", market_type="cn") is None
