import sys
from types import SimpleNamespace

import pytest

from app.services.kline_service import KlineService


def _rows(start, end):
    return [
        {
            "stock_date": start,
            "open": 10,
            "close": 11,
            "high": 12,
            "low": 9,
        },
        {
            "stock_date": end,
            "open": 11,
            "close": 12,
            "high": 13,
            "low": 10,
        },
    ]


class _DfcfApi:
    def __init__(self):
        self.calls = []

    def get_search_list_by_stock_code(self, stock_code, _page_size):
        if stock_code == "AAPL":
            return [{"code": stock_code, "market": "105", "shortName": "Apple"}]
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


def test_database_source_returns_all_rows_in_requested_date_range():
    service = KlineService(dfcf_api=_DfcfApi())
    service.read_internal_kline_data = lambda **_kwargs: [
        *_rows("2024-01-01", "2024-01-02"),
        *_rows("2024-01-03", "2024-01-04"),
    ]

    rows = service.get_kline_data(
        "600000", "cn", 2, data_source="database", start_date="2024-01-01", end_date="2024-01-04"
    )

    assert [row["stock_date"] for row in rows] == [
        "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
    ]


def test_database_source_filters_internal_rows_by_requested_date_range():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    service.read_internal_kline_data = lambda **_kwargs: [
        *_rows("2023-12-29", "2024-01-01"),
        *_rows("2024-01-31", "2024-02-01"),
    ]

    rows = service.get_kline_data(
        "600000", "cn", 2, data_source="database", start_date="2024-01-01", end_date="2024-01-31"
    )

    assert not dfcf.calls
    assert [row["stock_date"] for row in rows] == ["2024-01-01", "2024-01-31"]


def test_kline_dates_are_normalized_to_yyyy_mm_dd_before_range_filtering():
    service = KlineService(dfcf_api=_DfcfApi())
    service.read_internal_kline_data = lambda **_kwargs: [
        {
            "stock_date": "2024-01-01 00:00:00",
            "open": 10,
            "close": 11,
            "high": 12,
            "low": 9,
        },
        {
            "stock_date": "2024/01/31",
            "open": 11,
            "close": 12,
            "high": 13,
            "low": 10,
        },
    ]

    rows = service.get_kline_data(
        "600000", "cn", 1, data_source="database", start_date="2024-01-01", end_date="2024-01-31"
    )

    assert [row["stock_date"] for row in rows] == ["2024-01-01", "2024-01-31"]


def test_non_cn_en_markets_never_access_internal_kline_service(monkeypatch):
    service = KlineService(dfcf_api=_DfcfApi())
    service.stock_client = type("Client", (), {
        "stock_data": type("Source", (), {"get_data_all_list": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not read"))})(),
        "stock_data_us": type("Source", (), {"get_data_all_list": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not read"))})(),
    })()

    assert service.read_internal_kline_data(stock_code="7203", market_type="jp") == []
    assert service.write_internal_kline_data([], stock_code="7203", market_type="jp", adjust_type="forward") == []


def test_default_dfcf_source_uses_eastmoney_after_search():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    service.read_internal_kline_data = lambda **_kwargs: _rows("2024-01-01", "2024-01-31")

    rows = service.get_kline_data(
        "600000", "cn", 100, start_date="2024-01-01", end_date="2024-01-31"
    )

    assert dfcf.calls == [("600000", "1", 100, {"kline_type": "101", "adjust_type": None})]
    assert {row["data_source"] for row in rows} == {"dfcf"}


def test_database_source_falls_back_to_dfcf_and_persists_external_rows():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    persisted = []
    service.read_internal_kline_data = lambda **_kwargs: _rows("2024-01-10", "2024-01-31")
    service.write_internal_kline_data = lambda rows, **kwargs: persisted.append((rows, kwargs))

    rows = service.get_kline_data(
        "600000", "cn", 100, data_source="database", start_date="2024-01-01", end_date="2024-01-31"
    )

    assert dfcf.calls == [("600000", "1", 100, {"kline_type": "101", "adjust_type": None})]
    assert rows[0]["stock_name"] == "浦发银行"
    assert rows[0]["data_source"] == "dfcf"
    assert persisted[0][1]["source"] == "dfcf"


def test_external_source_is_normalized_and_persisted():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    persisted = []
    service.write_internal_kline_data = lambda rows, **kwargs: persisted.append((rows, kwargs))

    rows = service.get_kline_data("600000.SS", "cn", 100, data_source="dfcf")

    assert dfcf.calls == [("600000", "1", 100, {"kline_type": "101", "adjust_type": None})]
    assert rows[0]["stock_code"] == "600000.SH"
    assert rows[0]["stock_name"] == "浦发银行"
    assert rows[0]["open"] == 10.0
    assert rows[0]["close"] == 11.0
    assert rows[0]["high"] == 12.0
    assert rows[0]["low"] == 9.0
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

    rows = service.get_kline_data("600519.SS", "cn", 1, data_source="tdx", adjust_type="forward")

    assert _TdxClient.calls == [("sh", "600519", "daily", 1, "qfq")]
    assert rows[0]["stock_name"] == "Moutai"
    assert rows[0]["stock_date"] == "2024-01-31"
    assert rows[0]["volume"] == 100.0
    assert rows[0]["amount"] == 160000.0
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

    rows = service.get_kline_data("AAPL.US", "en", 2, data_source="qq", exchange_market="105", stock_name="Apple")

    assert qq_api.request == (
        "AAPL",
        "105",
        {"limit": 2, "kline_type": "101", "adjust_type": None, "market_type": "en"},
    )
    assert {row["stock_code"] for row in rows} == {"AAPL.US"}


def test_kline_type_is_forwarded_to_dfcf_and_qq():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)

    service.get_kline_data("600000", "cn", 5, data_source="dfcf", kline_type="30")

    assert dfcf.calls[-1][3]["kline_type"] == "30"

    class _QqRecorder:
        def __init__(self):
            self.kwargs = None

        def get_stock_kline_data(self, stock_code, exchange, **kwargs):
            self.kwargs = kwargs
            return _rows("2024-01-01", "2024-01-31")

    recorder = _QqRecorder()
    service = KlineService(dfcf_api=_DfcfApi(), qq_api=recorder)
    service.get_kline_data("600000", "cn", 5, data_source="qq", kline_type="5")

    assert recorder.kwargs["kline_type"] == "5"


def test_minute_kline_skips_internal_read_and_write():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)
    service.read_internal_kline_data = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("分钟周期不应读内部K线库")
    )
    service.write_internal_kline_data = lambda rows, **kwargs: (_ for _ in ()).throw(
        AssertionError("分钟周期不应写内部K线库")
    )

    rows = service.get_kline_data("600000", "cn", 5, data_source="dfcf", kline_type="5")

    assert dfcf.calls[-1][3]["kline_type"] == "5"
    assert rows


def test_minute_kline_keeps_root_datetime():
    class _MinuteDfcfApi:
        def get_search_list_by_stock_code(self, stock_code, _page_size):
            return [{"code": stock_code, "market": "1", "shortName": "浦发银行"}]

        def get_stock_kline_data(self, stock_code, market, limit, **kwargs):
            return [
                {"stock_date": "2024-01-01 09:30", "open": 10, "close": 11, "high": 12, "low": 9,
                 "volume": 100, "amount": 1100, "vwap": 11.0},
                {"stock_date": "2024-01-01 10:00", "open": 11, "close": 12, "high": 13, "low": 10,
                 "volume": 100, "amount": 1150, "vwap": 11.5},
            ]

    service = KlineService(dfcf_api=_MinuteDfcfApi())

    rows = service.get_kline_data("600000", "cn", 5, data_source="dfcf", kline_type="1")

    assert [row["stock_datetime"] for row in rows] == ["2024-01-01 09:30", "2024-01-01 10:00"]
    assert {row["stock_date"] for row in rows} == {"2024-01-01"}


def test_normalize_stock_date_supports_compact_datetime():
    assert KlineService._normalize_stock_date("202609301500") == "2026-09-30"
    assert KlineService._normalize_stock_date("20260930") == "2026-09-30"
    assert KlineService._normalize_stock_datetime("202609301500") == "2026-09-30 15:00"
    assert KlineService._normalize_stock_datetime("20260930150030") == "2026-09-30 15:00"
    assert KlineService._normalize_stock_datetime("2026-09-30") == ""
    assert KlineService._normalize_stock_datetime("2026-09-30 15:00") == "2026-09-30 15:00"


def _daily_rows_for_aggregation():
    """两周日线：09-21~09-25（周一至周五）、09-28~09-30（周一至周三）。"""
    rows = []
    for date, open_, close_, high, low, volume, amount in [
        ("2026-09-21", 10.0, 10.5, 10.8, 9.9, 100, 1050),
        ("2026-09-22", 10.5, 10.4, 10.6, 10.2, 110, 1140),
        ("2026-09-23", 10.4, 10.8, 11.0, 10.3, 120, 1290),
        ("2026-09-24", 10.8, 11.0, 11.2, 10.7, 130, 1420),
        ("2026-09-25", 11.0, 11.2, 11.5, 10.9, 140, 1560),
        ("2026-09-28", 11.2, 11.5, 11.6, 11.1, 150, 1700),
        ("2026-09-29", 11.5, 11.4, 11.7, 11.3, 160, 1830),
        ("2026-09-30", 11.4, 11.6, 11.8, 11.3, 170, 1960),
    ]:
        rows.append({
            "stock_code": "600000.SH",
            "stock_name": "浦发银行",
            "stock_date": date,
            "open": open_,
            "close": close_,
            "high": high,
            "low": low,
            "volume": volume,
            "amount": amount,
        })
    return rows


def test_week_kline_is_aggregated_from_daily_for_daily_only_source():
    class _AkshareApi:
        def __init__(self):
            self.calls = []

        def get_stock_kline_data(self, stock_code, exchange, limit=None, adjust_type=None,
                                 market_type=None, start_date=None, end_date=None):
            self.calls.append(limit)
            return _daily_rows_for_aggregation()

    akshare = _AkshareApi()
    service = KlineService(dfcf_api=_DfcfApi())
    service._akshare_api = akshare

    rows = service.get_kline_data("600000", "cn", 3, data_source="akshare", kline_type="102")

    # 日线拉取条数按周放大（3×7），akshare 不接收周K周期
    assert akshare.calls[-1] == 21
    assert len(rows) == 2
    first = rows[0]
    assert first["stock_date"] == "2026-09-25"  # 组内最后交易日
    assert first["open"] == 10.0
    assert first["close"] == 11.2
    assert first["high"] == 11.5
    assert first["low"] == 9.9
    assert first["volume"] == 600.0
    assert first["amount"] == 6460.0
    assert first["vwap"] == round(6460.0 / 600.0, 3)


def test_month_kline_is_aggregated_from_daily_for_daily_only_source():
    class _AkshareApi:
        def get_stock_kline_data(self, stock_code, exchange, limit=None, adjust_type=None,
                                 market_type=None, start_date=None, end_date=None):
            return _daily_rows_for_aggregation()

    service = KlineService(dfcf_api=_DfcfApi())
    service._akshare_api = _AkshareApi()

    rows = service.get_kline_data("600000", "cn", 5, data_source="akshare", kline_type="103")

    assert len(rows) == 1  # 两天跨月数据全在 9 月 → 一个月K
    only = rows[0]
    assert only["stock_date"] == "2026-09-30"
    assert only["open"] == 10.0
    assert only["close"] == 11.6
    assert only["high"] == 11.8
    assert only["low"] == 9.9


def test_week_kline_is_native_for_dfcf_without_aggregation():
    dfcf = _DfcfApi()
    service = KlineService(dfcf_api=dfcf)

    service.get_kline_data("600000", "cn", 5, data_source="dfcf", kline_type="102")

    # 原生源直传周K：条数不放大、kline_type 透传 102
    assert dfcf.calls[-1][2] == 5
    assert dfcf.calls[-1][3]["kline_type"] == "102"
