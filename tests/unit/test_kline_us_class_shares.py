from app.services.kline_service import KlineService


def _kline_rows(stock_code="BRK_B"):
    return [{
        "stock_code": stock_code,
        "stock_date": "2024-01-02",
        "open": 350.0,
        "high": 355.0,
        "low": 349.0,
        "close": 354.0,
        "volume": 1000,
        "amount": 354000.0,
    }]


class _SearchKlineDfcfApi:
    def __init__(self):
        self.search_keywords: list[str] = []
        self.kline_calls: list[tuple[str, str]] = []

    def get_search_list_by_stock_code(self, keyword, _page_size):
        self.search_keywords.append(keyword)
        return [{
            "code": "BRK_B",
            "shortName": "伯克希尔哈撒韦-B",
            "market": "106",
            "securityTypeName": "美股",
            "status": 10,
        }]

    def get_stock_kline_data(self, stock_code, stock_type, limit=100, kline_type="101", adjust_type=None):
        self.kline_calls.append((stock_code, stock_type))
        return _kline_rows(stock_code)


class _YahooApi:
    def __init__(self):
        self.codes: list[str] = []

    def get_kline_data(self, stock_code, *_args, **_kwargs):
        self.codes.append(stock_code)
        return _kline_rows(stock_code)


class _QQApi:
    def __init__(self):
        self.codes: list[str] = []

    def get_stock_kline_data(self, stock_code, *_args, **_kwargs):
        self.codes.append(stock_code)
        return _kline_rows(stock_code)


def test_dfcf_kline_converts_us_class_share_to_eastmoney_code(monkeypatch):
    dfcf_api = _SearchKlineDfcfApi()
    service = KlineService(dfcf_api=dfcf_api, yahoo_api=_YahooApi())
    monkeypatch.setattr(service, "read_internal_kline_data", lambda **_kwargs: [])

    rows = service.get_kline_data(
        "BRK-B.US", "en", 1,
        data_source="dfcf",
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert dfcf_api.search_keywords == ["BRK_B"]
    assert dfcf_api.kline_calls == [("BRK_B", "106")]
    assert rows[0]["stock_code"] == "BRK-B.US"


def test_yahoo_kline_uses_hyphen_us_class_share_ticker(monkeypatch):
    yahoo_api = _YahooApi()
    service = KlineService(dfcf_api=_SearchKlineDfcfApi(), yahoo_api=yahoo_api)
    monkeypatch.setattr(service, "read_internal_kline_data", lambda **_kwargs: [])

    rows = service.get_kline_data(
        "BRK_B", "en", 1,
        data_source="yahoo",
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert yahoo_api.codes == ["BRK-B"]
    assert rows[0]["stock_code"] == "BRK-B.US"


def test_qq_kline_uses_dot_us_class_share_ticker(monkeypatch):
    qq_api = _QQApi()
    service = KlineService(
        dfcf_api=_SearchKlineDfcfApi(), qq_api=qq_api, yahoo_api=_YahooApi(),
    )
    monkeypatch.setattr(service, "read_internal_kline_data", lambda **_kwargs: [])

    rows = service.get_kline_data(
        "BRK-B.US", "en", 1,
        data_source="qq",
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert qq_api.codes == ["BRK.B"]
    assert rows[0]["stock_code"] == "BRK-B.US"


def test_internal_kline_read_uses_canonical_us_base_code(monkeypatch):
    service = KlineService(dfcf_api=_SearchKlineDfcfApi(), yahoo_api=_YahooApi())
    seen: dict = {}

    def fake_read(**kwargs):
        seen.update(kwargs)
        return _kline_rows("BRK-B")

    monkeypatch.setattr(service, "read_internal_kline_data", fake_read)

    rows = service.get_kline_data(
        "BRK_B.US", "en", 1,
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert seen["stock_code"] == "BRK-B"
    assert rows[0]["stock_code"] == "BRK-B.US"
