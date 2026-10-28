"""进程内存归还工具（process_memory）单元测试。"""

from app.utils import process_memory


class _FakeLibc:
    def __init__(self, exc=None):
        self.calls: list[int] = []
        self._exc = exc

    def malloc_trim(self, pad):
        self.calls.append(pad)
        if self._exc:
            raise self._exc


def test_trim_is_noop_without_libc(monkeypatch):
    monkeypatch.setattr(process_memory, "_LIBC", None)
    assert process_memory.trim_process_memory() is False


def test_trim_calls_malloc_trim_with_zero(monkeypatch):
    fake = _FakeLibc()
    monkeypatch.setattr(process_memory, "_LIBC", fake)
    assert process_memory.trim_process_memory() is True
    assert fake.calls == [0]


def test_trim_swallows_libc_error(monkeypatch):
    monkeypatch.setattr(process_memory, "_LIBC", _FakeLibc(RuntimeError("boom")))
    assert process_memory.trim_process_memory() is False


def test_current_rss_parses_vmrss(monkeypatch, tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmRSS:\t  123456 kB\n", encoding="ascii")
    monkeypatch.setattr(process_memory, "_PROC_STATUS_PATH", str(status))
    assert process_memory.current_rss_mb() == 120.6


def test_current_rss_returns_none_when_unreadable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        process_memory, "_PROC_STATUS_PATH", str(tmp_path / "missing")
    )
    assert process_memory.current_rss_mb() is None
