import pytest

from app.services.stock_search_service import StockSearchService


class _DfcfApi:
    def get_search_list_by_stock_code(self, _keyword, _page_size):
        return [
            {"code": "00700", "shortName": "腾讯控股", "market": "116", "status": 10},
            {"code": "7203", "shortName": "丰田汽车", "market": "176", "status": 10},
            {"code": "AAPL", "shortName": "Apple", "market": "105", "status": 10},
        ]


def test_search_stocks_filters_by_normalized_market_type():
    service = StockSearchService(dfcf_api=_DfcfApi())

    results = service.search_stocks("测试", market_type="hk")

    assert [(item["code"], item["market_type"], item["exchange_market"]) for item in results] == [
        ("0700.HK", "hk", "116"),
    ]


def test_resolve_stock_requires_exact_code_in_requested_market():
    service = StockSearchService(dfcf_api=_DfcfApi())

    resolved = service.resolve_stock("7203", "jp")

    assert resolved["name"] == "丰田汽车"
    assert resolved["exchange_market"] == "176"

    with pytest.raises(ValueError, match="未找到香港（hk）市场股票代码 7203"):
        service.resolve_stock("7203", "hk")


def test_resolve_hong_kong_stock_accepts_four_digit_code():
    service = StockSearchService(dfcf_api=_DfcfApi())

    resolved = service.resolve_stock("0700", "hk")

    assert resolved["code"] == "0700.HK"
    assert resolved["exchange_market"] == "116"


def test_search_stocks_rejects_unknown_market_type():
    with pytest.raises(ValueError, match="market_type"):
        StockSearchService(dfcf_api=_DfcfApi()).search_stocks("腾讯", market_type="invalid")


def test_single_search_route_returns_all_markets(app_factory, monkeypatch):
    app = app_factory
    monkeypatch.setenv("AUTH_ENABLED", "false")
    captured = {}

    def fake_search(self, keyword, *, market_type=None, page_size):
        captured.update(keyword=keyword, market_type=market_type, page_size=page_size)
        return [
            {
                "code": "QQQ", "name": "Invesco QQQ", "market_type": "en",
                "exchange_market": "105", "security_type_name": "", "source": "codetable",
            },
            {
                "code": "000001", "name": "平安银行", "market_type": "cn",
                "exchange_market": "0", "security_type_name": "", "source": "codetable",
            },
        ]

    monkeypatch.setattr(StockSearchService, "search_stocks", fake_search)
    response = app.test_client().get("/api/search-stocks?q=腾讯&market_type=hk&page_size=8")

    assert response.status_code == 200
    assert captured == {"keyword": "腾讯", "market_type": None, "page_size": 8}
    payload = response.get_json()
    assert payload["status"] == "success"
    assert [item["code"] for item in payload["data"]["results"]] == ["QQQ", "000001"]
    assert [rule.rule for rule in app.url_map.iter_rules() if "search-stocks" in rule.rule] == [
        "/api/search-stocks",
    ]
