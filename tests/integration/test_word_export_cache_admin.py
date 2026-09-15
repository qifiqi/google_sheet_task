"""管理端 Word 导出缓存接口：列表、按任务定向清理与全清。"""

from io import BytesIO

import pytest
from pydantic import BaseModel

from app.utils.ttl_cache import get_or_build_word_export

REPORT_URL = "/api/exports/backtest-reports/word"
LIST_URL = "/admin/api/word-export-cache"
CLEAR_URL = "/admin/api/word-export-cache/clear"


class _CachePayload(BaseModel):
    """任意 pydantic 载荷即可参与缓存（键来自规范化 model_dump）。"""

    marker: str = ""

# Schema 强制 returns/task_id 三选一：走 returns 来源时载荷没有 task_id。
_REPORT_PAYLOAD = {
    "report_type": "RPT-S",
    "title": "缓存管理测试",
    "returns": [
        {"date": "2024-01-01", "index_return": 0, "start_return": 0},
        {"date": "2024-01-02", "index_return": 1, "start_return": 0.5},
    ],
}


@pytest.fixture
def cache_client(app_factory, monkeypatch):
    """关鉴权的测试客户端 + 桩掉 Word 生成（记录调用次数）。"""
    app = app_factory
    monkeypatch.setenv("AUTH_ENABLED", "false")
    calls = []

    def fake_generate_word(payload):
        calls.append(1)
        return "r.docx", BytesIO(b"data")

    monkeypatch.setattr(
        "app.services.export_service.strategy_backtest_report_service.generate_word",
        fake_generate_word,
    )
    return app.test_client(), calls


def test_list_reports_entry_metadata(cache_client):
    client, calls = cache_client
    assert client.post(REPORT_URL, json=_REPORT_PAYLOAD).status_code == 200
    assert client.post(REPORT_URL, json=_REPORT_PAYLOAD).status_code == 200
    assert len(calls) == 1  # 第二次命中缓存

    body = client.get(LIST_URL).get_json()
    assert body["status"] == "success"
    assert body["data"]["ttl_minutes"] >= 0
    assert len(body["data"]["entries"]) == 1
    entry = body["data"]["entries"][0]
    assert entry["title"] == "缓存管理测试"
    assert entry["filename"] == "r.docx"
    assert entry["expired"] is False


def test_targeted_clear_by_task_id_and_clear_all(cache_client):
    client, _calls = cache_client
    assert client.post(REPORT_URL, json=_REPORT_PAYLOAD).status_code == 200
    # 另造一条带 task_id 的缓存（模拟 RPT-M 按任务生成的报告）。
    get_or_build_word_export(
        _CachePayload(marker="task-report"),
        lambda: ("m.docx", BytesIO(b"m")),
        meta={"task_id": "task-cache-2", "title": "任务报告"},
    )

    cleared = client.post(CLEAR_URL, json={"task_id": "task-cache-2"})
    assert cleared.get_json()["data"]["removed"] == 1
    remaining = client.get(LIST_URL).get_json()["data"]["entries"]
    assert len(remaining) == 1 and remaining[0]["task_id"] is None

    cleared_all = client.post(CLEAR_URL, json={})
    assert cleared_all.get_json()["data"]["removed"] == 1
    assert client.get(LIST_URL).get_json()["data"]["entries"] == []


def test_clear_with_unknown_task_id_removes_nothing(cache_client):
    client, _calls = cache_client
    assert client.post(REPORT_URL, json=_REPORT_PAYLOAD).status_code == 200

    cleared = client.post(CLEAR_URL, json={"task_id": "not-exists"})
    assert cleared.get_json()["data"]["removed"] == 0
    assert len(client.get(LIST_URL).get_json()["data"]["entries"]) == 1
