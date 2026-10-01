"""GET /api/klines（K线查询接口）集成回归：信封、字段投影与参数校验。"""

import pytest

from app.routes import stock_api as stock_api_module


class _FakeKlineService:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_kline_data(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return list(self.rows)


def _kline_rows():
    return [
        {
            "stock_code": "600000.SH",
            "stock_name": "浦发银行",
            "stock_date": "2024-01-01 09:30",
            "stock_datetime": "2024-01-01 09:30",
            "open": 10.0,
            "close": 11.0,
            "high": 12.0,
            "low": 9.0,
            "volume": 100000.0,
            "amount": 1100000.0,
            "vwap": 11.0,
            "amplitude": 30.0,
            "pct_change": 10.0,
            "change": 1.0,
            "turnover_rate": 1.5,
            "data_source": "dfcf",
            "timestamp": "2024-01-01 15:00:00",
        },
        {
            "stock_code": "600000.SH",
            "stock_name": "浦发银行",
            "stock_date": "2024-01-02",
            "stock_datetime": "",
            "open": 11.0,
            "close": 12.0,
            "high": 13.0,
            "low": 10.0,
            "volume": 120000.0,
            "amount": 1320000.0,
            "vwap": 11.0,
            "amplitude": 27.27,
            "pct_change": 9.09,
            "change": 1.0,
            "turnover_rate": 1.8,
            "data_source": "dfcf",
            "timestamp": "2024-01-02 15:00:00",
        },
    ]


@pytest.fixture()
def _api_user(app_factory, monkeypatch):
    # 单 Token 模式：本地登录/JWT 已退役；AUTH_ENABLED=false 下以 mock 用户
    # 验证 K线接口契约（匿名 401 行为由 test_klines_requires_login 单独覆盖）。
    monkeypatch.setenv("AUTH_ENABLED", "false")
    yield {"headers": {}}


@pytest.fixture()
def _fake_kline_service(monkeypatch):
    fake = _FakeKlineService(_kline_rows())
    monkeypatch.setattr(stock_api_module, "_kline_service", fake)
    return fake


def test_klines_requires_login(app_factory):
    client = app_factory.test_client()

    response = client.get("/api/klines?stock_code=600000")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["status"] == "error"


def test_klines_returns_standard_rows(app_factory, _api_user, _fake_kline_service):
    client = app_factory.test_client()

    response = client.get(
        "/api/klines?stock_code=600000&market_type=cn&data_source=dfcf&kline_type=1&limit=100",
        headers=_api_user["headers"],
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    data = payload["data"]
    # 分钟行展示日期取根级时间，日线行为普通日期。
    assert [row["stock_date"] for row in data["rows"]] == ["2024-01-01 09:30", "2024-01-02"]
    assert data["rows"][0]["open"] == 10.0
    assert "timestamp" not in data["rows"][0]
    assert data["stock_code"] == "600000.SH"
    assert data["data_source"] == "dfcf"
    assert data["kline_type"] == "1"
    args, kwargs = _fake_kline_service.calls[0]
    assert args[0] == "600000"
    assert kwargs["kline_type"] == "1"
    assert kwargs["data_source"] == "dfcf"


def test_klines_normalizes_numeric_adjust_type(app_factory, _api_user, _fake_kline_service):
    """前端直发 dfcf 数字复权码，路由归一为内部英文词；缺省不强转（各源缺省语义不同）。"""
    client = app_factory.test_client()

    client.get(
        "/api/klines?stock_code=600000&data_source=tdx&adjust_type=1",
        headers=_api_user["headers"],
    )
    client.get(
        "/api/klines?stock_code=600000&data_source=dfcf&adjust_type=0",
        headers=_api_user["headers"],
    )
    client.get(
        "/api/klines?stock_code=600000&data_source=akshare",
        headers=_api_user["headers"],
    )

    forwarded = [kwargs.get("adjust_type") for _args, kwargs in _fake_kline_service.calls]
    assert forwarded == ["forward", "none", None]
    payload = app_factory.test_client().get(
        "/api/klines?stock_code=600000&adjust_type=2",
        headers=_api_user["headers"],
    ).get_json()
    assert payload["data"]["adjust_type"] == "back"


def test_klines_rejects_minute_period_on_daily_only_source(app_factory, _api_user, _fake_kline_service):
    client = app_factory.test_client()

    response = client.get(
        "/api/klines?stock_code=600000&data_source=akshare&kline_type=5",
        headers=_api_user["headers"],
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "分钟" in payload["message"]
    assert not _fake_kline_service.calls


def test_klines_rejects_unknown_data_source(app_factory, _api_user, _fake_kline_service):
    client = app_factory.test_client()

    response = client.get(
        "/api/klines?stock_code=600000&data_source=sina",
        headers=_api_user["headers"],
    )

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_klines_rejects_missing_stock_code(app_factory, _api_user, _fake_kline_service):
    client = app_factory.test_client()

    response = client.get("/api/klines", headers=_api_user["headers"])

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert not _fake_kline_service.calls


def test_klines_rejects_limit_out_of_range(app_factory, _api_user, _fake_kline_service):
    client = app_factory.test_client()

    response = client.get(
        "/api/klines?stock_code=600000&limit=20000",
        headers=_api_user["headers"],
    )

    assert response.status_code == 400
    assert not _fake_kline_service.calls
