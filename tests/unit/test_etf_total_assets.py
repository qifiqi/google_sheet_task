"""ETF 资产总数统一入口：市场分发、代码转换与降级行为。"""

import pytest

from app.utils import akshare_api, yf_api
from app.utils.etf_total_assets import get_etf_total_assets


class _FakeYFApi:
    """记录调用并按预设返回/抛错的雅虎替身。"""

    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc
        self.calls = []

    def get_total_assets(self, ticker):
        self.calls.append(ticker)
        if self.exc is not None:
            raise self.exc
        return self.value


def test_overseas_dispatches_to_yahoo_and_converts_ticker(monkeypatch):
    fake = _FakeYFApi(value=353240930304.0)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("QQQ.US", "en") == 353240930304.0
    assert fake.calls == ["QQQ"]


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


def test_empty_code_returns_none_without_dispatch(monkeypatch):
    fake = _FakeYFApi(value=1.0)
    monkeypatch.setattr(yf_api, "YFApi", lambda: fake)
    assert get_etf_total_assets("   ", "en") is None
    assert fake.calls == []


def test_cn_branch_hits_akshare_reserved_stub():
    # A股保留调用位：真实 AkshareApi 恒 None 且不触网；无 market_type 的纯数字代码同样路由到 cn。
    assert get_etf_total_assets("510300.SH", "cn") is None
    assert get_etf_total_assets("510300") is None


def test_yf_total_assets_parses_and_degrades(monkeypatch):
    api = yf_api.YFApi()

    monkeypatch.setattr(
        yf_api.yf, "Ticker", lambda symbol: type("T", (), {"info": {"totalAssets": "353240930304"}})()
    )
    assert api.get_total_assets("QQQ") == 353240930304.0

    monkeypatch.setattr(yf_api.yf, "Ticker", lambda symbol: type("T", (), {"info": {}})())
    assert api.get_total_assets("AAPL") is None

    def _boom(symbol):
        raise RuntimeError("network")

    monkeypatch.setattr(yf_api.yf, "Ticker", _boom)
    assert api.get_total_assets("QQQ") is None


def test_akshare_total_assets_reserved_stub_returns_none():
    assert akshare_api.AkshareApi().get_total_assets("510300.SH", market_type="cn") is None
