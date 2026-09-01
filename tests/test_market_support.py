import pytest

from app.services.kline_service import KlineService
from app.utils.dfcf_api import DFCJStockApi
from app.utils.market import market_type_from_eastmoney, normalize_stock_code, yahoo_symbol
from app.utils.return_series import build_return_series_fields


@pytest.mark.parametrize(
    ("market", "expected"),
    [
        ("116", "hk"), ("177", "kr"), ("176", "jp"), ("155", "uk"),
        ("185", "de"), ("186", "fr"),
    ],
)
def test_eastmoney_market_codes_have_business_market_types(market, expected):
    assert market_type_from_eastmoney(market) == expected


@pytest.mark.parametrize(
    ("stock_code", "market_type", "expected"),
    [
        ("RY", "ca", "RY.TO"), ("005930", "kr", "005930.KS"),
        ("7203", "jp", "7203.T"), ("00700", "hk", "0700.HK"),
        ("SHEL", "uk", "SHEL.L"), ("MC", "fr", "MC.PA"), ("SAP", "de", "SAP.DE"),
        ("005930.KQ", "kr", "005930.KQ"),
        ("600519", "cn", "600519.SS"),
        ("000001", "cn", "000001.SZ"),
        ("830000", "cn", "830000.BJ"),
        ("AAPL", "en", "AAPL"),
        ("D05", "sg", "D05.SI"),
        ("BHP", "au", "BHP.AX"),
        ("1155", "my", "1155.KL"),
    ],
)
def test_yahoo_symbol_maps_supported_markets(stock_code, market_type, expected):
    assert yahoo_symbol(stock_code, market_type) == expected


def test_standard_us_stock_code_uses_us_suffix_but_yahoo_ticker_does_not():
    assert normalize_stock_code("AAPL", "en") == "AAPL.US"
    assert yahoo_symbol("AAPL.US", "en") == "AAPL"


def test_normalize_stock_code_does_not_turn_a_legacy_name_into_us_ticker():
    assert normalize_stock_code("威腾电气", "en") == "威腾电气"


@pytest.mark.parametrize(
    ("stock_code", "market_type", "expected"),
    [
        ("600519", "cn", "600519.SS"),
        ("000001", "cn", "000001.SZ"),
        ("AAPL", "en", "AAPL.US"),
        ("RY", "ca", "RY.TO"),
    ],
)
def test_return_series_uses_yahoo_stock_code(stock_code, market_type, expected):
    fields = build_return_series_fields(
        [{"date": "2026-01-01", "index_return": 0, "start_return": 0}],
        stock_code=stock_code,
        stock_name=stock_code,
        market_type=market_type,
    )
    assert fields["stock_code"] == expected


class _DfcfApi:
    def get_search_list_by_stock_code(self, stock_code, _page_size):
        return [{"code": stock_code, "market": "116", "shortName": "腾讯控股"}]


class _YahooApi:
    def __init__(self):
        self.stock_code = None

    def get_kline_data(self, stock_code, *_args, **_kwargs):
        self.stock_code = stock_code
        return [{
            "stock_code": stock_code,
            "stock_date": "2024-01-02",
            "stock_kp": 10,
            "stock_sp": 11,
            "stock_zg": 12,
            "stock_zd": 9,
        }]


def test_yahoo_kline_uses_direct_market_ticker_mapping():
    yahoo_api = _YahooApi()
    service = KlineService(dfcf_api=_DfcfApi(), yahoo_api=yahoo_api)

    rows = service.get_kline_data("00700", "hk", 1, data_source="yahoo")

    assert yahoo_api.stock_code == "0700.HK"
    assert rows[0]["stock_code"] == "0700.HK"


class _EmptyDfcfApi(_DfcfApi):
    def get_search_list_by_stock_code(self, _stock_code, _page_size):
        return []


def test_yahoo_kline_falls_back_to_direct_market_ticker_when_search_is_empty():
    yahoo_api = _YahooApi()
    service = KlineService(dfcf_api=_EmptyDfcfApi(), yahoo_api=yahoo_api)

    rows = service.get_kline_data("7203", "jp", 1, data_source="yahoo")

    assert yahoo_api.stock_code == "7203.T"
    assert rows[0]["stock_code"] == "7203.T"


def test_yahoo_direct_ticker_mapping_supports_canada_suffix():
    yahoo_api = _YahooApi()
    service = KlineService(dfcf_api=_EmptyDfcfApi(), yahoo_api=yahoo_api)

    rows = service.get_kline_data("RY", "ca", 1, data_source="yahoo")

    assert yahoo_api.stock_code == "RY.TO"
    assert rows[0]["stock_code"] == "RY.TO"


def test_eastmoney_hong_kong_vwap_does_not_apply_a_share_volume_multiplier():
    api = DFCJStockApi()
    line = "2024-01-02,500.435,507.229,511.111,497.523,1000,500000,2.13,6.794,0.0,0.0"

    row = api._parse_kline_data(line, "00700", stock_type="116")

    assert row["stock_cjl"] == 1000
    assert row["stock_vwap"] == 500.0


def test_eastmoney_a_share_vwap_keeps_hand_to_share_conversion():
    api = DFCJStockApi()
    line = "2024-01-02,10.123,11.567,12.444,9.222,500,110000,3.45,10.55,1.98,0.55"

    row = api._parse_kline_data(line, "600000", stock_type="1")

    assert row["stock_cjl"] == 50000
    assert row["stock_vwap"] == 2.2


def test_meta_enums_returns_supported_stock_markets(app_factory):
    response = app_factory.test_client().get("/api/meta/enums")

    assert response.status_code == 200
    markets = response.get_json()["data"]["stock_markets"]
    assert [item["value"] for item in markets] == [
        "cn", "en", "ca", "kr", "jp", "hk", "uk", "fr", "de", "sg", "au", "my",
    ]
    assert {item["value"]: item["label"] for item in markets}["au"] == "澳大利亚"
    assert {item["value"]: item["label"] for item in markets}["my"] == "马来西亚"


@pytest.mark.parametrize(
    "template_name",
    [
        "google_sheet_c4/create.html",
        "google_sheet_c5/create.html",
        "google_sheet_c7/create.html",
        "google_sheet_c31/create.html",
        "backtest_training/create.html",
    ],
)
def test_c_series_create_pages_load_market_select_from_meta_api(app_factory, template_name):
    app_factory.jinja_env.get_template(template_name)
    source, _filename, _uptodate = app_factory.jinja_loader.get_source(
        app_factory.jinja_env,
        template_name,
    )

    assert '<select class="form-select" id="market_type"></select>' in source
    assert "loadStockMarkets" in source
    assert "market_type_cn" not in source
