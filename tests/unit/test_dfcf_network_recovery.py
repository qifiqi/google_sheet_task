from __future__ import annotations

from datetime import datetime as real_datetime, timedelta

import pytest
from requests.exceptions import ProxyError, SSLError

from app.services.backtest_training_service import BacktestTrainingService
from app.services.stock_search_service import StockSearchService
import app.services.backtest_training_service as backtest_training_service
from app.services.google_sheet_service_C7 import GoogleSheetService as GoogleSheetServiceC7
from app.utils.dfcf_api import DFCJStockApi
from app.utils.task_error_utils import RetryableNetworkTaskError


class _FixedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025, 1, 10)


def _kline_rows(start_date: str, end_date: str):
    current = real_datetime.strptime(start_date, "%Y-%m-%d").date()
    end = real_datetime.strptime(end_date, "%Y-%m-%d").date()
    rows = []
    while current <= end:
        rows.append({
            "stock_date": current.strftime("%Y-%m-%d"),
            "close": 10,
            "open": 9,
            "vwap": 12,
        })
        current += timedelta(days=1)
    return rows


def test_backtest_search_service_resolves_cn_stock_name_to_code():
    """旧的 _resolve_cn_stock_quote 已由统一 StockSearchService 取代。"""
    service = StockSearchService(dfcf_api=_FakeDfcfApi(
        search_results=[{"code": "002230", "market": "0", "shortName": "科大讯飞"}]
    ))

    results = service.search_stocks("科大讯飞")

    assert results[0]["code"] == "002230.SZ"
    assert results[0]["market_type"] == "cn"


class _FakeDfcfApi:
    """按需返回搜索/K线数据的东方财富 API 替身。"""

    def __init__(self, search_results=None, kline_rows=None):
        self.search_results = search_results or []
        self.kline_rows = kline_rows or []

    def get_search_list_by_stock_code(self, *_args, **_kwargs):
        return list(self.search_results)

    def get_stock_kline_data(self, *_args, **_kwargs):
        return list(self.kline_rows)


class _FakeKlineService:
    """直接返回预置 K 线的 KlineService 替身，绕过证券解析。"""

    def __init__(self, rows):
        self._rows = rows

    def get_kline_data(self, *_args, **_kwargs):
        return list(self._rows)

    def build_price_rows(self, klines, price_mode, **kwargs):
        from app.services.kline_service import KlineService

        return KlineService.build_price_rows(klines, price_mode, **kwargs)

def test_backtest_rethrows_network_error_as_retryable():
    service = BacktestTrainingService({}, "task-id")

    try:
        service._raise_retryable_network_error(
            ProxyError("Unable to connect to proxy"),
            "批量数据处理网络请求失败",
        )
    except RetryableNetworkTaskError as exc:
        assert "批量数据处理网络请求失败" in str(exc)
    else:
        raise AssertionError("expected RetryableNetworkTaskError")


def test_c7_rethrows_ssl_error_as_retryable_network_error():
    service = GoogleSheetServiceC7.__new__(GoogleSheetServiceC7)

    with pytest.raises(RetryableNetworkTaskError, match="批量数据处理网络请求失败"):
        service._raise_retryable_network_error(
            SSLError("EOF occurred in violation of protocol"),
            "批量数据处理网络请求失败",
        )


def test_backtest_full_years_accept_string_values(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(backtest_training_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(
        service, "kline_service", _FakeKlineService(_kline_rows("2023-01-01", "2025-01-10"))
    )

    combinations, column_a_length, kline_map = service._get_all_parameters(
        ["2024"],
        [],
        [["0.0350%", "1"]],
        "688361",
    )

    assert combinations == [{
        "parameter": ["0.0350%", "1"],
        "stock_code": "688361",
        "year": 2024,
        "Kline_key": 2024,
    }]
    assert len(kline_map[2024]) == 366
    assert column_a_length > len(kline_map[2024])


def test_backtest_missing_kline_range_raises_readable_error():
    service = BacktestTrainingService({}, "task-id")

    with pytest.raises(ValueError, match="K线区间 2024 没有可用数据"):
        service._require_kline_data("688361", 2024, None)


def test_backtest_recent_years_use_configured_end_date(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(backtest_training_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(
        service, "kline_service", _FakeKlineService(_kline_rows("2019-04-01", "2025-01-10"))
    )

    combinations, _column_a_length, kline_map = service._get_all_parameters(
        [],
        [5],
        [["param-a", "param-b"]],
        "688361",
        end_date="2024-04-23",
    )

    assert combinations == [{
        "parameter": ["param-a", "param-b"],
        "stock_code": "688361",
        "year": "2024-2019",
        "Kline_key": "2024-2019",
    }]
    assert kline_map["2024-2019"][0]["stock_date"] == "2019-04-23"
    assert kline_map["2024-2019"][-1]["stock_date"] == "2024-04-23"


def test_backtest_recent_years_allow_short_listing_history(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(backtest_training_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(
        service, "kline_service", _FakeKlineService(_kline_rows("2022-01-19", "2026-05-21"))
    )

    combinations, _column_a_length, kline_map = service._get_all_parameters(
        [],
        [5],
        [["param-a", "param-b"]],
        "CEG",
        end_date="2026-05-15",
    )

    assert combinations == [{
        "parameter": ["param-a", "param-b"],
        "stock_code": "CEG",
        "year": "2026-2021",
        "Kline_key": "2026-2021",
    }]
    assert kline_map["2026-2021"][0]["stock_date"] == "2022-01-19"
    assert kline_map["2026-2021"][-1]["stock_date"] == "2026-05-15"


def test_backtest_include_full_year_range_replaces_individual_full_years(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(backtest_training_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(
        service, "kline_service", _FakeKlineService(_kline_rows("2022-01-04", "2025-01-10"))
    )

    combinations, column_a_length, kline_map = service._get_all_parameters(
        [2022, 2023, 2024, 2025],
        [],
        [["param-a", "param-b"], ["param-c", "param-d"]],
        "688361",
        include_full_year_range=True,
        end_date="2025-01-08",
    )

    assert combinations == [
        {
            "parameter": ["param-a", "param-b"],
            "stock_code": "688361",
            "year": "2022-2025",
            "Kline_key": "2022-2025",
        },
        {
            "parameter": ["param-c", "param-d"],
            "stock_code": "688361",
            "year": "2022-2025",
            "Kline_key": "2022-2025",
        },
    ]
    assert sorted(kline_map) == ["2022-2025"]
    assert kline_map["2022-2025"][0]["stock_date"] == "2022-01-04"
    assert kline_map["2022-2025"][-1]["stock_date"] == "2025-01-08"
    assert column_a_length > len(kline_map["2022-2025"])


def test_backtest_include_full_year_range_requires_full_years():
    service = BacktestTrainingService({}, "task-id")

    with pytest.raises(ValueError, match="include_full_year_range=true 时必须传入 full_years"):
        service._get_all_parameters(
            [],
            [],
            [["param-a", "param-b"]],
            "688361",
            include_full_year_range=True,
        )


def test_backtest_include_full_year_range_validates_end_date():
    service = BacktestTrainingService({}, "task-id")

    with pytest.raises(ValueError, match="end_date 格式无效"):
        service._get_all_parameters(
            [2024],
            [],
            [["param-a", "param-b"]],
            "688361",
            include_full_year_range=True,
            end_date="20240521",
        )


def test_dfcf_proxy_failure_invalidates_proxy_and_resets_session(monkeypatch):
    api = DFCJStockApi()
    events = []

    class _ProxyManager:
        def get_best_proxy(self, force_refresh=False):
            events.append(("get_best_proxy", force_refresh))
            return {"http": "http://user:pass@proxy:8080", "https": "http://user:pass@proxy:8080"}

        def invalidate_proxy(self):
            events.append(("invalidate_proxy", None))

    class _Session:
        headers = {}
        trust_env = False
        verify = None

        def close(self):
            events.append(("close", None))

        def get(self, *args, **kwargs):
            raise ProxyError("Unable to connect to proxy")

    api.proxy_manager = _ProxyManager()
    api.session = _Session()
    monkeypatch.setattr(api, "_reset_session", lambda: events.append(("reset_session", None)))

    try:
        api._DFCJStockApi__get("https://push2his.eastmoney.com", use_proxy=True)
    except ProxyError:
        pass

    assert ("invalidate_proxy", None) in events
    assert ("reset_session", None) in events
    assert ("get_best_proxy", True) in events


def test_dfcf_search_reraises_network_errors(monkeypatch):
    api = DFCJStockApi()

    def fail_request(*args, **kwargs):
        raise ProxyError("Unable to connect to proxy")

    monkeypatch.setattr(api, "_DFCJStockApi__get", fail_request)

    try:
        api._search_codetable("科大讯飞", 10)
    except ProxyError:
        pass
    else:
        raise AssertionError("expected ProxyError")
