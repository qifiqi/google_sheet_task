import pytest

from app.utils.market import (
    normalize_stock_code,
    to_eastmoney_ticker,
    to_qq_ticker,
    to_yahoo_ticker,
)


@pytest.mark.parametrize(
    "stock_code",
    ["BRK-B.US", "BRK_B.US", "BRK.B.US", "BRK-B", "BRK_B", "BRK.B"],
)
def test_us_class_share_codes_normalize_to_project_standard(stock_code):
    assert normalize_stock_code(stock_code, "en") == "BRK-B.US"


def test_us_regular_ticker_keeps_hyphenless_standard_code():
    assert normalize_stock_code("AAPL.US", "en") == "AAPL.US"
    assert normalize_stock_code("AAPL", "en") == "AAPL.US"


def test_non_us_markets_keep_existing_code_rules():
    assert normalize_stock_code("600519", "cn") == "600519.SH"
    assert normalize_stock_code("0700", "hk") == "0700.HK"
    assert normalize_stock_code("005930.KQ", "kr") == "005930.KQ"


def test_us_class_share_code_still_rejects_non_code_text():
    assert normalize_stock_code("威腾电气", "en") == "威腾电气"


@pytest.mark.parametrize(
    "stock_code",
    ["BRK-B.US", "BRK_B.US", "BRK.B.US", "BRK-B", "BRK_B", "BRK.B"],
)
def test_us_class_share_maps_to_eastmoney_underscore(stock_code):
    assert to_eastmoney_ticker(stock_code, "en") == "BRK_B"


def test_eastmoney_ticker_for_other_markets_strips_only_project_suffix():
    assert to_eastmoney_ticker("AAPL.US", "en") == "AAPL"
    assert to_eastmoney_ticker("600519.SH", "cn") == "600519"
    assert to_eastmoney_ticker("0700.HK", "hk") == "0700"


@pytest.mark.parametrize(
    "stock_code",
    ["BRK-B.US", "BRK_B.US", "BRK.B.US", "BRK-B", "BRK_B", "BRK.B"],
)
def test_us_class_share_maps_to_yahoo_hyphen(stock_code):
    assert to_yahoo_ticker(stock_code, "en") == "BRK-B"


@pytest.mark.parametrize(
    "stock_code",
    ["BRK-B.US", "BRK_B.US", "BRK.B.US", "BRK-B", "BRK_B", "BRK.B"],
)
def test_us_class_share_maps_to_qq_dot(stock_code):
    assert to_qq_ticker(stock_code, "en") == "BRK.B"


def test_qq_ticker_for_other_markets_strips_only_project_suffix():
    assert to_qq_ticker("AAPL.US", "en") == "AAPL"
    assert to_qq_ticker("600519.SH", "cn") == "600519"
    assert to_qq_ticker("0700.HK", "hk") == "0700"
