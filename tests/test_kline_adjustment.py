from urllib.parse import parse_qs, urlparse

import pandas as pd

from app.services.backtest_multi_product_service import normalize_multi_product_config
import app.services.google_sheet_service_C4 as google_sheet_service_C4
from app.services.google_sheet_service_C4 import GoogleSheetService as C4GoogleSheetService
from app.utils.dfcf_api import DFCJStockApi
from app.utils.kline_adjustment import (
    eastmoney_fqt,
    normalize_kline_adjustment,
    yahoo_adjust_flags,
)
from app.utils.yf_api import YFApi


def test_kline_adjustment_defaults_and_aliases():
    assert normalize_kline_adjustment(None) == "forward"
    assert normalize_kline_adjustment("前复权") == "forward"
    assert normalize_kline_adjustment("2") == "back"
    assert normalize_kline_adjustment("不复权") == "none"


def test_eastmoney_fqt_mapping_defaults_to_forward():
    assert eastmoney_fqt(None) == "1"
    assert eastmoney_fqt("forward") == "1"
    assert eastmoney_fqt("back") == "2"
    assert eastmoney_fqt("none") == "0"


def test_yahoo_adjust_flags_mapping():
    assert yahoo_adjust_flags("forward") == {"auto_adjust": True, "back_adjust": False}
    assert yahoo_adjust_flags("back") == {"auto_adjust": False, "back_adjust": True}
    assert yahoo_adjust_flags("none") == {"auto_adjust": False, "back_adjust": False}


def test_eastmoney_url_uses_selected_fqt():
    api = DFCJStockApi()

    url = api._build_eastmoney_url("1", "600000", 300, adjust_type="back")
    params = parse_qs(urlparse(url).query)

    assert params["fqt"] == ["2"]


def test_eastmoney_parse_kline_calculates_vwap_for_numeric_stock_code():
    api = DFCJStockApi()

    row = api._parse_kline_data(
        "2024-01-02,10,11,12,9,500,110000,3,10,1,0.5",
        "600000",
    )

    assert row["stock_cjl"] == 50000
    assert row["stock_cje"] == 110000
    assert row["stock_vwap"] == 2.2


def test_multi_product_normalize_preserves_product_kline_adjustment():
    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "products": [
            {
                "stock_code": "600000",
                "market_type": "cn",
                "kline_adjustment": "none",
                "ratio": "50",
                "sheet": {"spreadsheet_id": "sheet-1", "sheet_name": "data"},
                "parameters": [["1"]],
            },
            {
                "stock_code": "AAPL",
                "market_type": "us",
                "ratio": "50",
                "sheet": {"spreadsheet_id": "sheet-2", "sheet_name": "data"},
                "parameters": [["2"]],
            },
        ],
    }

    normalized = normalize_multi_product_config(config)

    assert normalized["products"][0]["kline_adjustment"] == "none"
    assert normalized["products"][1]["kline_adjustment"] == "forward"


def test_c4_us_market_uses_yahoo_adjustment(monkeypatch):
    calls = {}

    class FakeYFApi:
        def get_kline_data(self, stock_code, period, adjust_type=None):
            calls["yf"] = {
                "stock_code": stock_code,
                "period": period,
                "adjust_type": adjust_type,
            }
            return [
                {"stock_date": f"2023-12-{day:02d}", "stock_sp": 9, "stock_kp": 8}
                for day in range(1, 31)
            ] + [
                {"stock_date": "2024-01-01", "stock_sp": 10, "stock_kp": 9},
                {"stock_date": "2024-01-02", "stock_sp": 11, "stock_kp": 10},
            ]

    class FakeDFCFApi:
        def get_search_list_by_stock_code(self, *_args, **_kwargs):
            calls["dfcf_search"] = True
            return [{"securityTypeName": "美股", "market": "105"}]

        def get_stock_kline_data(self, *_args, **_kwargs):
            calls["dfcf_kline"] = True
            return []

    monkeypatch.setattr(google_sheet_service_C4, "YFApi", FakeYFApi)
    monkeypatch.setattr(google_sheet_service_C4, "DFCJStockApi", FakeDFCFApi)

    data, _column_a_length = C4GoogleSheetService._get_all_parameters(
        "AAPL",
        "total",
        "2024-01-02",
        "2024-01-01",
        "us",
        [],
        "back",
    )

    assert calls["yf"] == {
        "stock_code": "AAPL",
        "period": "10y",
        "adjust_type": "back",
    }
    assert "dfcf_search" not in calls
    assert "dfcf_kline" not in calls
    assert data[0]["kline"] == [
        {"stock_date": "2024-01-01", "stock_val": 10},
        {"stock_date": "2024-01-02", "stock_val": 11},
    ]


def test_yahoo_forward_adjustment_uses_adj_close_as_close():
    api = YFApi()
    frame = pd.DataFrame(
        {
            "Open": [10.0, 12.0],
            "High": [11.0, 13.0],
            "Low": [9.0, 11.0],
            "Close": [10.0, 12.0],
            "Adj Close": [20.0, 24.0],
            "Volume": [100, 200],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    adjusted = api._adjust_ticker_frame(frame, adjust_type="forward")

    assert adjusted["Close"].tolist() == [20.0, 24.0]
    assert adjusted["Adj Close"].tolist() == [20.0, 24.0]
    assert adjusted["Open"].tolist() == [20.0, 24.0]
    assert adjusted["High"].tolist() == [22.0, 26.0]
    assert adjusted["Low"].tolist() == [18.0, 22.0]


def test_yahoo_back_adjustment_bases_on_first_row():
    api = YFApi()
    frame = pd.DataFrame(
        {
            "Open": [10.0, 12.0],
            "High": [11.0, 13.0],
            "Low": [9.0, 11.0],
            "Close": [10.0, 12.0],
            "Adj Close": [20.0, 30.0],
            "Volume": [100, 200],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )

    adjusted = api._adjust_ticker_frame(frame, adjust_type="back")

    assert adjusted["Close"].tolist() == [10.0, 15.0]
    assert adjusted["Adj Close"].tolist() == [10.0, 15.0]
    assert adjusted["Open"].tolist() == [10.0, 15.0]
    assert adjusted["High"].tolist() == [11.0, 16.25]
    assert adjusted["Low"].tolist() == [9.0, 13.75]


def test_yahoo_parse_single_ticker_uses_ticker_hint_and_adjusted_close_for_cje():
    api = YFApi()
    frame = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.0],
            "Adj Close": [20.0],
            "Volume": [5],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )

    rows = api.parse_multiple_tickers(frame, adjust_type="forward", ticker_hint="AAPL")

    assert rows == [
        {
            "stock_code": "AAPL",
            "stock_date": "2024-01-01",
            "stock_kp": 20.0,
            "stock_sp": 20.0,
            "stock_zg": 22.0,
            "stock_zd": 18.0,
            "stock_cjl": 5,
            "stock_cje": 100.0,
            "stock_vwap": 20.0,
            "stock_zf": 22.22,
            "stock_zdf": 0.0,
            "stock_zde": 0.0,
            "stock_hsl": 0.0,
            "timestamp": rows[0]["timestamp"],
        }
    ]
