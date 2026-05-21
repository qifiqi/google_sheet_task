from __future__ import annotations

from requests.exceptions import ProxyError

from app.services.backtest_training_service import BacktestTrainingService
from app.utils.dfcf_api import DFCJStockApi
from app.utils.task_error_utils import RetryableNetworkTaskError, build_task_error_message


def test_build_task_error_message_marks_proxy_error_retryable():
    err = ProxyError("Unable to connect to proxy")

    message = build_task_error_message(err)

    assert message.startswith("[NETWORK_RETRYABLE]")
    assert "ProxyError" in message


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
