"""进程内统一 TTL 缓存：TTL 判活、LRU 淘汰与 Word 导出磁盘缓存回放。"""

import json
import os
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.utils import ttl_cache
from app.utils.ttl_cache import (
    TTLCache,
    clear_word_export_cache,
    get_or_build_word_export,
    list_word_export_cache,
)


class _Payload(BaseModel):
    a: int = 0
    b: str = ""


class _FakeClock:
    """可手动推进的单调钟，替代 time.monotonic 验证 TTL 过期。"""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(ttl_cache.time, "monotonic", clock)
    return clock


def test_get_or_set_reuses_cached_value_within_ttl(fake_clock):
    cache = TTLCache()
    calls = []

    def builder():
        calls.append(1)
        return "value"

    assert cache.get_or_set("k", builder, ttl_seconds=60) == "value"
    fake_clock.advance(59)
    assert cache.get_or_set("k", builder, ttl_seconds=60) == "value"
    assert len(calls) == 1


def test_get_or_set_rebuilds_after_ttl_expiry(fake_clock):
    cache = TTLCache()
    calls = []

    def builder():
        calls.append(len(calls))
        return f"value-{len(calls)}"

    assert cache.get_or_set("k", builder, ttl_seconds=60) == "value-1"
    fake_clock.advance(61)
    assert cache.get_or_set("k", builder, ttl_seconds=60) == "value-2"
    assert len(calls) == 2


def test_builder_exception_is_not_cached(fake_clock):
    cache = TTLCache()
    attempts = []

    def builder():
        attempts.append(1)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        cache.get_or_set("k", builder, ttl_seconds=60)
    assert cache.get_or_set("k", lambda: "ok", ttl_seconds=60) == "ok"
    assert len(attempts) == 1


def test_lru_evicts_oldest_beyond_capacity(fake_clock):
    cache = TTLCache(max_entries=2)
    cache.get_or_set("k1", lambda: 1, ttl_seconds=60)
    cache.get_or_set("k2", lambda: 2, ttl_seconds=60)
    # 访问 k1 提升其热度，随后插入 k3 时应淘汰 k2。
    cache.get_or_set("k1", lambda: 1, ttl_seconds=60)
    cache.get_or_set("k3", lambda: 3, ttl_seconds=60)

    assert cache.get_or_set("k1", lambda: "rebuilt", ttl_seconds=60) == 1
    assert cache.get_or_set("k2", lambda: "rebuilt", ttl_seconds=60) == "rebuilt"
    assert cache.get_or_set("k3", lambda: 3, ttl_seconds=60) == 3


def test_clear_drops_all_entries(fake_clock):
    cache = TTLCache()
    cache.get_or_set("k", lambda: 1, ttl_seconds=60)
    cache.clear()
    assert cache.get_or_set("k", lambda: "rebuilt", ttl_seconds=60) == "rebuilt"


def test_word_export_persists_file_and_replays_identical_payload(fake_clock, tmp_path):
    calls = []

    def builder():
        calls.append(1)
        return "报告.docx", BytesIO(b"docx-bytes")

    first_filename, first_buffer, first_size = get_or_build_word_export(_Payload(a=1, b="x"), builder)
    second_filename, second_buffer, second_size = get_or_build_word_export(_Payload(a=1, b="x"), builder)

    cache_dir = ttl_cache.word_export_cache_dir()
    files = {path.name for path in Path(cache_dir).iterdir()}
    assert len(calls) == 1
    # 缓存落盘：报告本体 + sidecar（记录原始下载文件名）。
    assert len([name for name in files if name.endswith(".docx")]) == 1
    assert len([name for name in files if name.endswith(".json")]) == 1
    # 首次为内存字节流，命中为磁盘文件句柄（send_file 流式下发），必须每次发新对象。
    assert isinstance(first_buffer, BytesIO)
    assert not isinstance(second_buffer, BytesIO)
    assert first_buffer is not second_buffer
    assert first_filename == second_filename == "报告.docx"
    assert first_buffer.getvalue() == second_buffer.read() == b"docx-bytes"
    assert (first_size, second_size) == (len(b"docx-bytes"), len(b"docx-bytes"))


def test_word_export_rebuilds_when_file_mtime_expires_ttl(fake_clock, tmp_path):
    calls = []

    def builder():
        calls.append(len(calls))
        return f"v{len(calls)}.docx", BytesIO(f"bytes-{len(calls)}".encode())

    get_or_build_word_export(_Payload(a=1), builder)
    docx_path = next(Path(ttl_cache.word_export_cache_dir()).glob("*.docx"))
    # 直接回拨 mtime 模拟落盘文件超过 TTL（磁盘判活对 wall clock）。
    old_stamp = os.path.getmtime(docx_path) - (ttl_cache.WORD_EXPORT_TTL_SECONDS + 60)
    os.utime(docx_path, (old_stamp, old_stamp))

    filename, buffer, _size = get_or_build_word_export(_Payload(a=1), builder)

    assert len(calls) == 2
    assert filename == "v2.docx"
    assert buffer.read() == b"bytes-2"


def test_word_export_sweeps_expired_files_on_next_call(fake_clock, tmp_path):
    cache_dir = Path(ttl_cache.word_export_cache_dir())
    cache_dir.mkdir(parents=True)
    stale = cache_dir / "stale.docx"
    stale.write_bytes(b"stale")
    old_stamp = os.path.getmtime(stale) - (ttl_cache.WORD_EXPORT_TTL_SECONDS + 60)
    os.utime(stale, (old_stamp, old_stamp))

    get_or_build_word_export(_Payload(a=1), lambda: ("r.docx", BytesIO(b"data")))

    assert not stale.exists()
    assert list(cache_dir.glob("*.docx"))


def test_word_export_rebuilds_when_sidecar_missing(fake_clock, tmp_path):
    calls = []

    def builder():
        calls.append(1)
        return "报告.docx", BytesIO(b"docx-bytes")

    get_or_build_word_export(_Payload(a=1), builder)
    sidecar = next(Path(ttl_cache.word_export_cache_dir()).glob("*.json"))
    sidecar.unlink()

    filename, _buffer, _size = get_or_build_word_export(_Payload(a=1), builder)

    # 缺 sidecar 视为条目不完整，重新生成并补齐。
    assert len(calls) == 2
    assert filename == "报告.docx"
    assert json.loads(next(Path(ttl_cache.word_export_cache_dir()).glob("*.json")).read_text(
        encoding="utf-8"))["filename"] == "报告.docx"


def test_word_export_key_ignores_nested_dict_order(fake_clock, tmp_path):
    calls = []

    def builder():
        calls.append(1)
        return "r.docx", BytesIO(b"docx-bytes")

    class _NestedPayload(BaseModel):
        metadata: dict = {}

    get_or_build_word_export(_NestedPayload(metadata={"title": "t", "risk": "1%"}), builder)
    get_or_build_word_export(_NestedPayload(metadata={"risk": "1%", "title": "t"}), builder)

    # 规范化 JSON 对嵌套字典键序不敏感：语义相同的请求命中同一份缓存文件。
    assert len(calls) == 1


def test_word_export_distinguishes_different_payloads_and_clear_resets(fake_clock, tmp_path):
    calls = []

    def builder_for(value):
        def builder():
            calls.append(value)
            return f"{value}.docx", BytesIO(value.encode())
        return builder

    get_or_build_word_export(_Payload(a=1), builder_for("a"))
    get_or_build_word_export(_Payload(a=2), builder_for("b"))
    assert len(calls) == 2

    clear_word_export_cache()
    assert not Path(ttl_cache.word_export_cache_dir()).exists()
    get_or_build_word_export(_Payload(a=1), builder_for("a"))
    assert len(calls) == 3


def test_word_export_meta_persisted_and_listed(fake_clock, tmp_path):
    get_or_build_word_export(
        _Payload(a=1),
        lambda: ("报告.docx", BytesIO(b"data")),
        meta={"title": "冒烟", "task_id": "task-9", "stock_codes": ["QQQ.US"]},
    )

    entries = list_word_export_cache()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["filename"] == "报告.docx"
    assert entry["title"] == "冒烟"
    assert entry["task_id"] == "task-9"
    assert entry["stock_codes"] == ["QQQ.US"]
    assert entry["size_bytes"] == 4
    assert entry["expired"] is False
    assert entry["created_at"]


def test_word_export_targeted_clear_by_task_id(fake_clock, tmp_path):
    calls = []

    def builder_for(tag):
        def builder():
            calls.append(tag)
            return f"{tag}.docx", BytesIO(tag.encode())
        return builder

    get_or_build_word_export(_Payload(a=1), builder_for("a"), meta={"task_id": "t1"})
    get_or_build_word_export(_Payload(a=2), builder_for("b"), meta={"task_id": "t2"})

    assert clear_word_export_cache(task_id="t1") == 1
    assert {entry["task_id"] for entry in list_word_export_cache()} == {"t2"}
    # t1 的报告缓存已被定向清理，同载荷再导出会重新生成。
    get_or_build_word_export(_Payload(a=1), builder_for("a"), meta={"task_id": "t1"})
    assert calls == ["a", "b", "a"]


def test_word_export_clear_only_expired(fake_clock, tmp_path):
    get_or_build_word_export(_Payload(a=1), lambda: ("old.docx", BytesIO(b"o")), meta={"task_id": "t1"})
    get_or_build_word_export(_Payload(a=2), lambda: ("new.docx", BytesIO(b"n")), meta={"task_id": "t2"})
    stale = next(
        Path(ttl_cache.word_export_cache_dir()) / f"{entry['key']}.docx"
        for entry in list_word_export_cache() if entry["task_id"] == "t1"
    )
    old_stamp = os.path.getmtime(stale) - (ttl_cache.WORD_EXPORT_TTL_SECONDS + 60)
    os.utime(stale, (old_stamp, old_stamp))

    assert clear_word_export_cache(only_expired=True) == 1
    assert {entry["task_id"] for entry in list_word_export_cache()} == {"t2"}


def test_word_export_bypasses_cache_when_ttl_disabled(fake_clock, tmp_path):
    calls = []

    def builder():
        calls.append(1)
        return "r.docx", BytesIO(b"data")

    get_or_build_word_export(_Payload(a=1), builder, ttl_seconds=0)
    get_or_build_word_export(_Payload(a=1), builder, ttl_seconds=0)

    assert len(calls) == 2
    assert list_word_export_cache() == []
