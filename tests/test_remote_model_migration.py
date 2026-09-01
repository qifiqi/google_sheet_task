"""关键模型迁移到远端 Repository 的定向单元测试。"""

from __future__ import annotations

import pytest

from app.repositories.backtest_product_result_cache_repository import BacktestProductResultCacheRepository
from app.repositories.sdk_client import SdkDataAccessError
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.services import model_summary_service


class FakeAdapter:
    """记录 SDK 调用并返回预设响应，测试不访问真实网络。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, group_name, operation, payload):
        self.calls.append((group_name, operation, dict(payload)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_stock_metadata_find_latest_uses_remote_business_filters():
    adapter = FakeAdapter([{
        "items": [{"id": 7, "stock_code": "600519", "market_type": "cn", "raw_json": "{}"}],
        "total": 1,
    }])

    record = StockMetadataRepository(adapter).find_latest("600519", "cn")

    assert record["id"] == 7
    assert adapter.calls[0] == (
        "param_stock_metadata",
        "get_data_by_page_list",
        {
            "page_index": 1,
            "page_size": 1,
            "order_field": "updated_at",
            "order_type": "desc",
            "stock_code": "600519",
            "market_type": "cn",
        },
    )


def test_stock_metadata_find_latest_handles_no_record_and_remote_failure():
    assert StockMetadataRepository(FakeAdapter([{"items": [], "total": 0}])).find_latest("AAPL", "us") is None
    with pytest.raises(SdkDataAccessError, match="远端失败"):
        StockMetadataRepository(FakeAdapter([SdkDataAccessError("远端失败")])).find_latest("AAPL", "us")


def test_cache_business_key_query_pages_without_local_database():
    adapter = FakeAdapter([
        {"items": [{"batch_id": "other", "cache_key": "other"}], "total": 2},
        {"items": [{"batch_id": "batch-1", "cache_key": "key-1", "result_json": "{}"}], "total": 2},
    ])

    record = BacktestProductResultCacheRepository(adapter).find_by_business_key("batch-1", "key-1")

    assert record["result_json"] == {}
    assert [call[2]["page_index"] for call in adapter.calls] == [1, 2]


def test_cache_business_key_query_handles_no_record_and_remote_failure():
    assert BacktestProductResultCacheRepository(FakeAdapter([{"items": [], "total": 0}])).find_by_business_key("batch-1", "missing") is None
    with pytest.raises(SdkDataAccessError, match="缓存服务失败"):
        BacktestProductResultCacheRepository(FakeAdapter([SdkDataAccessError("缓存服务失败")])).find_by_business_key("batch-1", "key-1")


class FakeSummaryRepository:
    """替代远端汇总接口，验证服务层不会回退本地 ORM。"""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def get_data_summary(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeUser:
    """只提供汇总查询所需的权限对象接口。"""

    def get_permissions(self):
        return {"task:view", "google_sheet:c3"}


def test_summary_query_uses_remote_summary_for_normal_and_empty_results(monkeypatch):
    repository = FakeSummaryRepository({
        "items": [{"task_id": "task-1", "metrics": {"I15": 0.2}}],
        "total": 1,
        "summary": {"stock_count": 1, "task_count": 1},
        "summary_type": "stock",
    })
    monkeypatch.setattr(model_summary_service, "_summary_index_repository", repository)
    monkeypatch.setattr(model_summary_service, "filter_task_types_by_action", lambda *_: ["google_sheet"])

    payload = model_summary_service.ModelSummaryService().query(FakeUser(), {
        "page": 1,
        "per_page": 20,
        "task_type": "google_sheet",
        "stock_code": "600519",
        "summary_type": "stock",
    })

    assert payload["items"][0]["task_id"] == "task-1"
    assert repository.calls[0]["task_types"] == ["google_sheet"]
    assert repository.calls[0]["stock_keyword"] == "600519"
    assert repository.calls[0]["is_best"] is True

    repository.result = {"items": [], "total": 0, "summary": {}, "summary_type": "task"}
    empty = model_summary_service.ModelSummaryService().query(FakeUser(), {"task_type": "google_sheet"})
    assert empty["items"] == []
    assert empty["pagination"]["total"] == 0


def test_summary_query_propagates_remote_failure(monkeypatch):
    monkeypatch.setattr(model_summary_service, "_summary_index_repository", FakeSummaryRepository(error=SdkDataAccessError("汇总服务失败")))
    monkeypatch.setattr(model_summary_service, "filter_task_types_by_action", lambda *_: ["google_sheet"])

    with pytest.raises(SdkDataAccessError, match="汇总服务失败"):
        model_summary_service.ModelSummaryService().query(FakeUser(), {"task_type": "google_sheet"})
