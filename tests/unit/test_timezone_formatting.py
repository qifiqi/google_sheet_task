from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.utils.formatting import to_beijing_iso


def test_to_beijing_iso_converts_aware_utc():
    value = datetime(2026, 10, 23, 6, 45, 18, tzinfo=timezone.utc)
    assert to_beijing_iso(value) == "2026-10-23T14:45:18+08:00"


def test_to_beijing_iso_none():
    assert to_beijing_iso(None) is None


def test_to_beijing_iso_naive_uses_server_local_time():
    naive = datetime(2026, 10, 23, 6, 45, 18)
    expected = naive.astimezone().astimezone(ZoneInfo("Asia/Shanghai"))
    assert datetime.fromisoformat(to_beijing_iso(naive)) == expected
