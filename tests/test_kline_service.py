import sys
from types import SimpleNamespace

import pytest

from app.services.kline_service import KlineService


def _rows(start, end):
    return [
        {
            "stock_date": start,
            "stock_kp": 10,
            "stock_sp": 11,
            "stock_zg": 12,
            "stock_zd": 9,
        },
        {
            "stock_date": end,
            "stock_kp": 11,
            "stock_sp": 12,
            "stock_zg": 13,
            "stock_zd": 10,
        },
    ]


class _DfcfApi:
    def __init__(self):
        self.calls = []

    def get_search_list_by_stock_code(self, stock_code, _page_size):
        return [{"code": stock_code, "market": "1", "shortName": "浦发银行"}]

    def get_stock_kline_data(self, stock_code, market, limit, **kwargs):
        self.calls.append((stock_code, market, limit, kwargs))
        return _rows("2024-01-01", "2024-01-31")


def test_database_source_uses_internal_rows_when_range_is_covered():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    service.read_internal_kline_data = lambda **_kwargs: _rows("2024-01-01", "2024-01-31")

    rows = service.get_kline_data(
        "600000", "cn", 100, data_source="database", start_date="2024-01-01", end_date="2024-01-31"
    )

    assert not dfcf.calls
    assert [row["stock_name"] for row in rows] == ["", ""]
    assert {row["data_source"] for row in rows} == {"database"}


def test_default_dfcf_source_still_prefers_internal_rows():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    service.read_internal_kline_data = lambda **_kwargs: _rows("2024-01-01", "2024-01-31")

    rows = service.get_kline_data(
        "600000", "cn", 100, start_date="2024-01-01", end_date="2024-01-31"
    )

    assert not dfcf.calls
    assert {row["data_source"] for row in rows} == {"database"}


def test_database_source_falls_back_to_dfcf_and_persists_external_rows():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    persisted = []
    service.read_internal_kline_data = lambda **_kwargs: _rows("2024-01-10", "2024-01-31")
    service.write_internal_kline_data = lambda rows, **kwargs: persisted.append((rows, kwargs))

    rows = service.get_kline_data(
        "600000", "cn", 100, data_source="database", start_date="2024-01-01", end_date="2024-01-31"
    )

    assert dfcf.calls == [("600000", "1", 100, {"adjust_type": None})]
    assert rows[0]["stock_name"] == "浦发银行"
    assert rows[0]["data_source"] == "dfcf"
    assert persisted[0][1]["source"] == "dfcf"


def test_external_source_is_normalized_and_persisted():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    persisted = []
    service.write_internal_kline_data = lambda rows, **kwargs: persisted.append((rows, kwargs))

    rows = service.get_kline_data("600000", "cn", 100, data_source="dfcf")

    assert rows[0]["stock_code"] == "600000"
    assert rows[0]["stock_name"] == "浦发银行"
    assert rows[0]["stock_kp"] == 10.0
    assert rows[0]["stock_sp"] == 11.0
    assert rows[0]["stock_zg"] == 12.0
    assert rows[0]["stock_zd"] == 9.0
    assert persisted[0][1]["source"] == "dfcf"


def test_rejects_unknown_data_source():
    service = KlineService(dfcf_api=_DfcfApi())

    try:
        service.get_kline_data("600000", "cn", 100, data_source="unknown")
    except ValueError as exc:
        assert "kline_data_source" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_register_source_adds_source_without_changing_kline_service():
    service = KlineService(dfcf_api=_DfcfApi())
    service.read_internal_kline_data = lambda **_kwargs: []
    service.register_source("custom", lambda request: _rows("2024-01-01", "2024-01-02"))

    rows = service.get_kline_data("CUSTOM", "cn", 2, data_source="custom")

    assert len(rows) == 2
    assert {row["data_source"] for row in rows} == {"custom"}


class _TdxFrame:
    empty = False

    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class _TdxQuotes:
    empty = False

    class _Row:
        def get(self, key, default=None):
            return {"name": "Moutai"}.get(key, default)

    class _ILoc:
        @staticmethod
        def __getitem__(_index):
            return _TdxQuotes._Row()

    iloc = _ILoc()


class _TdxClient:
    calls = []

    @classmethod
    def from_best_host(cls):
        return cls()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_stock_kline(self, market, code, period, *, count, adjust):
        self.calls.append((market, code, period, count, adjust))
        return _TdxFrame([
            {
                "datetime": "2024-01-31 00:00:00",
                "open": 1600,
                "close": 1650,
                "high": 1660,
                "low": 1590,
                "vol": 100,
                "amount": 160000,
            }
        ])

    @staticmethod
    def get_stock_quotes(_stocks):
        return _TdxQuotes()


def test_tdx_source_fetches_a_share_daily_kline_and_persists(monkeypatch):
    tdx_module = SimpleNamespace(
        Adjust=SimpleNamespace(NONE="none", QFQ="qfq", HFQ="hfq"),
        MacClient=_TdxClient,
        Market=SimpleNamespace(SH="sh", SZ="sz", BJ="bj"),
        Period=SimpleNamespace(DAILY="daily"),
    )
    monkeypatch.setitem(sys.modules, "easy_tdx", tdx_module)
    _TdxClient.calls = []
    persisted = []
    service = KlineService(dfcf_api=_DfcfApi())
    service.write_internal_kline_data = lambda rows, **kwargs: persisted.append((rows, kwargs))

    rows = service.get_kline_data("600519", "cn", 1, data_source="tdx", adjust_type="forward")

    assert _TdxClient.calls == [("sh", "600519", "daily", 1, "qfq")]
    assert rows[0]["stock_name"] == "Moutai"
    assert rows[0]["stock_date"] == "2024-01-31"
    assert rows[0]["stock_cjl"] == 100.0
    assert rows[0]["stock_cje"] == 160000.0
    assert rows[0]["data_source"] == "tdx"
    assert persisted[0][1]["source"] == "tdx"


def test_tdx_source_rejects_non_cn_market():
    service = KlineService(dfcf_api=_DfcfApi())

    with pytest.raises(ValueError, match="仅支持 A股"):
        service.get_kline_data("AAPL", "en", 10, data_source="tdx")


def test_qq_source_passes_us_market_type_to_qq_api():
    class _QqApi:
        def __init__(self):
            self.request = None

        def get_stock_kline_data(self, stock_code, exchange, **kwargs):
            self.request = (stock_code, exchange, kwargs)
            return _rows("2024-01-01", "2024-01-31")

    qq_api = _QqApi()
    service = KlineService(dfcf_api=_DfcfApi(), qq_api=qq_api)

    service.get_kline_data("AAPL", "en", 2, data_source="qq", exchange_market="105", stock_name="Apple")

    assert qq_api.request == (
        "AAPL",
        "105",
        {"limit": 2, "adjust_type": None, "market_type": "en"},
    )
