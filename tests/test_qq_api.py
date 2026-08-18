from app.utils.qq_api import QQStockApi


class _Response:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_qq_us_kline_uses_us_symbol_and_us_volume_amount_units():
    api = QQStockApi()
    captured = {}
    def fake_get(_url, params):
        captured["params"] = params
        return _Response({
            "data": {
                "usAAPL": {
                    "hfqday": [{"value": [
                        "2026-08-14", "306.00", "305.93", "307.49", "304.30",
                        "28229375", {}, "0.19", "8632093700",
                    ]}],
                },
            },
        })

    api._get = fake_get

    rows = api.get_stock_kline_data(
        "AAPL",
        "105",
        limit=1,
        adjust_type="back",
        market_type="en",
    )

    assert captured["params"]["param"] == "usAAPL,day,,,1,hfq"
    assert rows == [{
        "stock_code": "AAPL",
        "stock_date": "2026-08-14",
        "stock_kp": 306.0,
        "stock_sp": 305.93,
        "stock_zg": 307.49,
        "stock_zd": 304.3,
        "stock_cjl": 28229375,
        "stock_cje": 8632093700.0,
        "stock_zf": 1.05,
        "stock_zdf": -0.02,
        "stock_zde": -0.07,
        "stock_hsl": 0.19,
        "timestamp": rows[0]["timestamp"],
    }]
