from datetime import date, timedelta

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
        "open": 306.0,
        "close": 305.93,
        "high": 307.49,
        "low": 304.3,
        "volume": 28229375,
        "amount": 8632093700.0,
        "amplitude": 1.05,
        "pct_change": -0.02,
        "change": -0.07,
        "turnover_rate": 0.19,
        "timestamp": rows[0]["timestamp"],
    }]


def _mk_qq_day_row(date_str):
    return [date_str, "10.00", "10.10", "10.20", "9.90", "1000", {}, "0.5", "10000"]


def test_qq_daily_kline_pagination_cursor_goes_to_end_slot():
    """日线多页翻页：游标必须写进 param 第4位(end)。

    fqkline 在 end 为空时忽略 start、恒返回最新一段；游标若放 start 位，
    第二页会原样重取最新一批，命中"游标未前进"提前终止，远期历史（如 2019 年）永远取不到。
    """
    api = QQStockApi()
    captured = []

    def fake_get(_url, params):
        captured.append(params["param"])
        if len(captured) == 1:
            items = [
                _mk_qq_day_row((date(2023, 1, 2) + timedelta(days=i)).isoformat())
                for i in range(640)
            ]
        else:
            items = [_mk_qq_day_row("2023-01-01")]
        return _Response({"data": {"sz000001": {"qfqday": items}}})

    api._get = fake_get
    rows = api.get_stock_kline_data("000001", "0", limit=641, kline_type="101", adjust_type="1")

    assert captured[0] == "sz000001,day,,,640,qfq"
    assert captured[1] == "sz000001,day,,2023-01-02,1,qfq"
    assert [r["stock_date"] for r in rows][:2] == ["2023-01-01", "2023-01-02"]
    assert len(rows) == 641
