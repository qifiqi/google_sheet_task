import app.routes.eastmoney_kline as eastmoney_kline_route


def test_eastmoney_kline_fallback_returns_page_compatible_rows(app_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    calls = {}

    class FakeApi:
        def get_stock_kline_data(self, stock_code, market, limit, **kwargs):
            calls.update(stock_code=stock_code, market=market, limit=limit, **kwargs)
            return [{
                "stock_date": "2025-01-02",
                "stock_kp": 10,
                "stock_sp": 11,
                "stock_zg": 12,
                "stock_zd": 9,
                "stock_cjl": 50000,
                "stock_cje": 110000,
                "stock_zf": 3,
                "stock_zdf": 10,
                "stock_zde": 1,
                "stock_hsl": 0.5,
            }]

    monkeypatch.setattr(eastmoney_kline_route, "DFCJStockApi", FakeApi)
    response = app_factory.test_client().get(
        "/eastmoney-kline/api/klines?secid=1.600000&klt=101&lmt=100&fqt=2"
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["klines"] == [
        "2025-01-02,10,11,12,9,500.0,110000,3,10,1,0.5"
    ]
    assert calls == {
        "stock_code": "600000",
        "market": "1",
        "limit": 100,
        "kline_type": "101",
        "adjust_type": "2",
    }


def test_eastmoney_kline_fallback_rejects_invalid_secid(app_factory, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")

    response = app_factory.test_client().get("/eastmoney-kline/api/klines?secid=invalid")

    assert response.status_code == 400
    assert response.get_json()["message"] == "证券标识格式无效"
