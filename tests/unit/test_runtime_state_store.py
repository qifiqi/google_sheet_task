"""任务运行态存储（app/services/task/runtime_state.py）单元测试。

FakeRedis 覆盖存储用到的最小命令集（pipeline 顺序回放）；回灌路径经
monkeypatch 替换仓储方法，全套件零网络、零 DB 依赖。
"""
import fnmatch

import pytest

from app.services.task import runtime_state
from app.services.task.runtime_state import (
    TaskRuntimeStateStore,
    configure_runtime_state_store,
    get_runtime_state_store,
    reconcile_all_runtime_states,
)


class FakePipeline:
    def __init__(self, client):
        self._client = client
        self._ops = []

    def hsetnx(self, key, field, value):
        self._ops.append(("hsetnx", key, field, value))
        return self

    def hset(self, key, mapping=None):
        self._ops.append(("hset", key, mapping))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    def lpush(self, key, value):
        self._ops.append(("lpush", key, value))
        return self

    def ltrim(self, key, start, stop):
        self._ops.append(("ltrim", key, start, stop))
        return self

    def delete(self, *keys):
        self._ops.append(("delete", keys))
        return self

    def run_pending(self):
        """按入队顺序回放命令，返回结果列表。"""
        results = []
        for op in self._ops:
            name = op[0]
            if name == "hsetnx":
                results.append(self._client.hsetnx(op[1], op[2], op[3]))
            elif name == "hset":
                results.append(self._client.hset(op[1], mapping=op[2]))
            elif name == "expire":
                results.append(self._client.expire(op[1], op[2]))
            elif name == "lpush":
                results.append(self._client.lpush(op[1], op[2]))
            elif name == "ltrim":
                results.append(self._client.ltrim(op[1], op[2], op[3]))
            elif name == "delete":
                results.append(self._client.delete(*op[1]))
        return results


# redis-py pipeline 的提交方法为惯用名，经类属性别名注入以匹配替身接口。
FakePipeline.execute = FakePipeline.run_pending  # noqa: B010


class FakeRedis:
    """redis-py 客户端最小替身：Hash/List/exists/scan/pipeline。"""

    def __init__(self):
        self.hashes = {}
        self.lists = {}

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.hashes:
                del self.hashes[key]
                deleted += 1
            if key in self.lists:
                del self.lists[key]
                deleted += 1
        return deleted

    def exists(self, key):
        return int(key in self.hashes or key in self.lists)

    def hset(self, key, mapping=None):
        self.hashes.setdefault(key, {}).update(
            {field: str(value) for field, value in (mapping or {}).items()}
        )
        return len(mapping or {})

    def hsetnx(self, key, field, value):
        entry = self.hashes.setdefault(key, {})
        if field in entry:
            return 0
        entry[field] = str(value)
        return 1

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return 1

    def ltrim(self, key, start, stop):
        entries = self.lists.get(key)
        if entries is None:
            return 0
        if stop < 0:
            stop = len(entries) + stop
        self.lists[key] = entries[start : stop + 1]
        return 1

    def lrange(self, key, start, stop):
        entries = self.lists.get(key, [])
        if stop < 0:
            stop = len(entries) + stop + 1
        return entries[start:stop]

    def expire(self, key, seconds):
        return 1

    def scan_iter(self, match=None, count=None):
        for key in list(self.hashes):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    def pipeline(self):
        return FakePipeline(self)


@pytest.fixture(autouse=True)
def _reset_singleton():
    configure_runtime_state_store(None)
    yield
    configure_runtime_state_store(None)


# ---- 进程内存后端 ----


def test_memory_backend_full_lifecycle():
    store = TaskRuntimeStateStore()

    assert store.has_state("t1") is False
    assert store.get_status_value("t1") is None

    store.mark_running("t1", current_step=7, total_steps=10)
    state = store.get_state("t1")
    assert state["status"] == "running"
    assert state["current_step"] == 7
    assert state["total_steps"] == 10
    assert store.get_status_value("t1") == "running"

    store.update_progress("t1", current_step=8)
    assert store.get_state("t1")["current_step"] == 8

    store.append_log("t1", "info", "第一条")
    store.append_log("t1", "warning", "第二条")
    logs = store.get_logs("t1")
    assert [log["message"] for log in logs] == ["第一条", "第二条"]

    assert store.request_cancel("t1") is True
    assert store.get_status_value("t1") == "cancelled"

    store.drop("t1")
    assert store.has_state("t1") is False
    assert store.get_logs("t1") == []


def test_memory_backend_progress_on_missing_state_creates_it():
    store = TaskRuntimeStateStore()
    store.update_progress("t1", current_step=3, total_steps=9)
    state = store.get_state("t1")
    assert state["status"] == "running"
    assert state["current_step"] == 3
    assert state["total_steps"] == 9


def test_memory_backend_request_cancel_without_state_is_noop():
    store = TaskRuntimeStateStore()
    assert store.request_cancel("t1") is False
    assert store.has_state("t1") is False


def test_memory_backend_log_cap():
    store = TaskRuntimeStateStore(log_max=5)
    for index in range(8):
        store.append_log("t1", "info", f"log-{index}")
    logs = store.get_logs("t1")
    assert len(logs) == 5
    assert [log["message"] for log in logs] == ["log-3", "log-4", "log-5", "log-6", "log-7"]


def test_memory_backend_get_states_and_active_ids():
    store = TaskRuntimeStateStore()
    store.mark_running("a")
    store.mark_running("b")
    states = store.get_states(["a", "b", "missing"])
    assert set(states) == {"a", "b"}
    assert sorted(store.list_active_ids()) == ["a", "b"]


# ---- Redis 后端（FakeRedis 替身）----


def test_redis_backend_lifecycle():
    store = TaskRuntimeStateStore(client=FakeRedis(), namespace="arb:test")
    store.mark_running("t1", current_step=2, total_steps=5)
    store.update_progress("t1", current_step=3)
    store.append_log("t1", "info", "r-log")

    state = store.get_state("t1")
    assert state["status"] == "running"
    assert state["current_step"] == 3
    assert state["total_steps"] == 5
    assert [log["message"] for log in store.get_logs("t1")] == ["r-log"]

    store.request_cancel("t1")
    assert store.get_status_value("t1") == "cancelled"

    store.drop("t1")
    assert store.has_state("t1") is False


def test_redis_backend_list_active_ids_parses_task_ids():
    client = FakeRedis()
    store = TaskRuntimeStateStore(client=client, namespace="arb:test")
    store.mark_running("task-a")
    store.mark_running("task-b")
    assert sorted(store.list_active_ids()) == ["task-a", "task-b"]


def test_redis_backend_mark_running_resets_previous_state():
    store = TaskRuntimeStateStore(client=FakeRedis(), namespace="arb:test")
    store.mark_running("t1", current_step=9, total_steps=9)
    store.update_progress("t1", current_step=10)
    # 上一轮遗留取消态后重新开跑：整键覆盖，进度按 DB 快照播种。
    store.request_cancel("t1")
    store.mark_running("t1", current_step=4, total_steps=9)
    state = store.get_state("t1")
    assert state["status"] == "running"
    assert state["current_step"] == 4


# ---- 快照回灌（仓储经 monkeypatch 替换）----


def test_sync_snapshot_flushes_progress_logs_and_drops(monkeypatch):
    store = TaskRuntimeStateStore(client=FakeRedis(), namespace="arb:test")
    store.mark_running("t1", current_step=1, total_steps=4)
    store.update_progress("t1", current_step=3)
    store.append_log("t1", "info", "运行日志")

    written = {}

    def fake_update_fields(task_id, **fields):
        written[task_id] = fields
        return {"id": task_id}

    flushed = {}

    def fake_create_logs(task_id, logs, commit=True):
        flushed[task_id] = logs
        return logs

    monkeypatch.setattr(runtime_state.task_repository, "update_fields", fake_update_fields)
    monkeypatch.setattr(runtime_state.task_log_repository, "create_logs", fake_create_logs)

    result = store.sync_snapshot("t1", status="completed")

    assert written["t1"]["status"] == "completed"
    assert written["t1"]["current_step"] == 3
    assert written["t1"]["total_steps"] == 4
    assert "end_time" in written["t1"]
    assert [row["message"] for row in flushed["t1"]] == ["运行日志"]
    assert result["flushed_logs"] == 1
    assert store.has_state("t1") is False


def test_sync_snapshot_without_state_is_noop(monkeypatch):
    store = TaskRuntimeStateStore()

    def fail_update_fields(*args, **kwargs):
        raise AssertionError("无运行态不应写库")

    monkeypatch.setattr(runtime_state.task_repository, "update_fields", fail_update_fields)
    assert store.sync_snapshot("t1", status="completed") is None


def test_sync_snapshot_without_status_only_syncs_progress(monkeypatch):
    store = TaskRuntimeStateStore(client=FakeRedis(), namespace="arb:test")
    store.mark_running("t1", current_step=2, total_steps=4)
    store.update_progress("t1", current_step=3)

    written = {}
    monkeypatch.setattr(
        runtime_state.task_repository,
        "update_fields",
        lambda task_id, **fields: written.setdefault(task_id, fields),
    )
    monkeypatch.setattr(
        runtime_state.task_log_repository, "create_logs", lambda task_id, logs, commit=True: []
    )

    store.sync_snapshot("t1")
    assert "status" not in written["t1"]
    assert written["t1"]["current_step"] == 3


def test_progress_fields_empty_without_state():
    store = TaskRuntimeStateStore()
    assert store.progress_fields("t1") == {}


def test_reconcile_all_runtime_states(monkeypatch):
    client = FakeRedis()
    store = TaskRuntimeStateStore(client=client, namespace="arb:test")
    configure_runtime_state_store(store)
    store.mark_running("t1", current_step=5, total_steps=9)
    store.update_progress("t1", current_step=6)
    store.append_log("t1", "info", "遗留日志")

    written = {}
    monkeypatch.setattr(
        runtime_state.task_repository,
        "update_fields",
        lambda task_id, **fields: written.setdefault(task_id, fields),
    )
    monkeypatch.setattr(
        runtime_state.task_log_repository,
        "create_logs",
        lambda task_id, logs, commit=True: logs,
    )

    assert reconcile_all_runtime_states() == 1
    assert written["t1"]["current_step"] == 6
    assert store.has_state("t1") is False


def test_singleton_defaults_and_configure():
    store = get_runtime_state_store()
    assert isinstance(store, TaskRuntimeStateStore)
    replacement = TaskRuntimeStateStore()
    configure_runtime_state_store(replacement)
    assert get_runtime_state_store() is replacement
