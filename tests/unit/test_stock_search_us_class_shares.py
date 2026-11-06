from datetime import datetime

from app.services.stock_search_service import StockSearchService


class _RecordingDfcfApi:
    def __init__(self):
        self.keywords: list[str] = []

    def get_search_list_by_stock_code(self, keyword, _page_size):
        self.keywords.append(keyword)
        if keyword == "BRK_B":
            return [{
                "code": "BRK_B",
                "shortName": "伯克希尔哈撒韦-B",
                "market": "106",
                "securityTypeName": "美股",
                "status": 10,
            }]
        return []


def test_search_stocks_converts_us_class_share_keyword_to_eastmoney():
    dfcf_api = _RecordingDfcfApi()
    service = StockSearchService(dfcf_api=dfcf_api)

    results = service.search_stocks("BRK-B.US", market_type="en")

    assert dfcf_api.keywords == ["BRK_B"]
    assert [(item["code"], item["market_type"], item["exchange_market"]) for item in results] == [
        ("BRK-B.US", "en", "106"),
    ]


def test_search_stocks_keeps_non_ticker_keyword_unchanged():
    dfcf_api = _RecordingDfcfApi()
    service = StockSearchService(dfcf_api=dfcf_api)

    service.search_stocks("伯克希尔", market_type="en")

    assert dfcf_api.keywords == ["伯克希尔"]


def test_resolve_stock_accepts_us_class_share_aliases():
    dfcf_api = _RecordingDfcfApi()
    service = StockSearchService(dfcf_api=dfcf_api)

    for stock_code in ("BRK-B.US", "BRK_B.US", "BRK.B.US", "BRK-B", "BRK_B", "BRK.B"):
        resolved = service.resolve_stock(stock_code, "en")
        assert resolved["code"] == "BRK-B.US"
        assert resolved["name"] == "伯克希尔哈撒韦-B"
        assert resolved["exchange_market"] == "106"

    assert dfcf_api.keywords == ["BRK_B"] * 6


def test_resolve_stock_hits_us_stock_meta_cache(app_factory):
    from app.extensions import db
    from app.models import StockMetadata

    with app_factory.app_context():
        now = datetime.now()
        db.session.execute(StockMetadata.__table__.insert().values(
            stock_code="BRK-B.US",
            stock_name="伯克希尔哈撒韦-B",
            market_type="us",
            exchange_market="106",
            security_type_name="美股",
            source="codetable",
            created_at=now,
            updated_at=now,
        ))
        db.session.commit()

        dfcf_calls = []
        service = StockSearchService(dfcf_api=type(
            "Spy",
            (),
            {"get_search_list_by_stock_code": staticmethod(
                lambda *args, **kwargs: dfcf_calls.append(args) or []
            )},
        )())

        resolved = service.resolve_stock("BRK-B.US", "en")

        assert dfcf_calls == []
        assert resolved["code"] == "BRK-B.US"
        assert resolved["exchange_market"] == "106"
        assert resolved["market_type"] == "en"


def test_resolve_legacy_us_symbol_hits_canonical_stock_meta_cache(app_factory):
    from app.extensions import db
    from app.models import StockMetadata

    with app_factory.app_context():
        now = datetime.now()
        db.session.execute(StockMetadata.__table__.insert().values(
            stock_code="BRK-B.US",
            stock_name="伯克希尔哈撒韦-B",
            market_type="us",
            exchange_market="106",
            security_type_name="美股",
            source="codetable",
            created_at=now,
            updated_at=now,
        ))
        db.session.commit()

        dfcf_calls = []
        service = StockSearchService(dfcf_api=type(
            "Spy",
            (),
            {"get_search_list_by_stock_code": staticmethod(
                lambda *args, **kwargs: dfcf_calls.append(args) or []
            )},
        )())

        resolved = service.resolve_stock("BRK_B", "en")

        assert dfcf_calls == []
        assert resolved["code"] == "BRK-B.US"
        assert resolved["exchange_market"] == "106"
