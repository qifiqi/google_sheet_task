from __future__ import annotations

from datetime import datetime as real_datetime, timedelta

import pytest
from requests.exceptions import ProxyError

from app.services.backtest_training_service import BacktestTrainingService
import app.services.backtest_training_service as backtest_training_service
from app.utils.dfcf_api import DFCJStockApi
from app.utils.task_error_utils import (
    GOOGLE_SHEET_EXECUTION_ERROR_PREFIX,
    RetryableNetworkTaskError,
    build_task_error_message,
)


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
            "stock_sp": 10,
            "stock_kp": 9,
        })
        current += timedelta(days=1)
    return rows


def test_build_task_error_message_marks_proxy_error_retryable():
    err = ProxyError("Unable to connect to proxy")

    message = build_task_error_message(err)

    assert message.startswith("[NETWORK_RETRYABLE]")
    assert "ProxyError" in message


def test_build_task_error_message_marks_google_sheet_timeout_retryable():
    err = RuntimeError("执行超时，未在规定时间内完成")

    message = build_task_error_message(err)

    assert message.startswith(GOOGLE_SHEET_EXECUTION_ERROR_PREFIX)
    assert "执行超时" in message


def test_backtest_resolves_cn_stock_name_to_code(monkeypatch):
    service = BacktestTrainingService({}, "task-id")

    monkeypatch.setattr(
        service.dfcf_api,
        "get_search_list_by_stock_code",
        lambda stock, page_size: [{"code": "002230", "market": "0"}],
    )

    resolved_code, market = service._resolve_cn_stock_quote("科大讯飞")

    assert resolved_code == "002230"
    assert market == "0"


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


def test_backtest_full_years_accept_string_values(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(backtest_training_service, "datetime", _FixedDatetime)
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: _kline_rows("2023-01-01", "2025-01-10"),
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
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: _kline_rows("2019-04-01", "2025-01-10"),
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
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: _kline_rows("2022-01-19", "2026-05-21"),
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
    monkeypatch.setattr(service, "_resolve_cn_stock_quote", lambda stock_code: (stock_code, "1"))
    monkeypatch.setattr(
        service.dfcf_api,
        "get_stock_kline_data",
        lambda _stock_code, _market, _limit, **_kwargs: _kline_rows("2022-01-04", "2025-01-10"),
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
