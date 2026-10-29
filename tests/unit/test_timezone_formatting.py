"""时间输出开关测试。

默认（开关关闭）必须与改动前的 naive isoformat 完全一致；打开后才转北京时间。
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.formatting import set_time_output_as_beijing, to_beijing_iso


@pytest.fixture(autouse=True)
def _reset_mode():
    yield
    set_time_output_as_beijing(False)


def test_default_mode_keeps_legacy_naive_output():
    set_time_output_as_beijing(False)
    value = datetime(2026, 10, 23, 6, 45, 18)
    assert to_beijing_iso(value) == "2026-10-23T06:45:18"


def test_default_mode_none():
    set_time_output_as_beijing(False)
    assert to_beijing_iso(None) is None


def test_beijing_mode_converts_aware_utc():
    set_time_output_as_beijing(True)
    value = datetime(2026, 10, 23, 6, 45, 18, tzinfo=timezone.utc)
    assert to_beijing_iso(value) == "2026-10-23T14:45:18+08:00"


def test_beijing_mode_naive_uses_server_local_time():
    set_time_output_as_beijing(True)
    naive = datetime(2026, 10, 23, 6, 45, 18)
    expected = naive.astimezone().astimezone(ZoneInfo("Asia/Shanghai"))
    assert datetime.fromisoformat(to_beijing_iso(naive)) == expected


def test_beijing_mode_none():
    set_time_output_as_beijing(True)
    assert to_beijing_iso(None) is None
