"""任务挂死检测的时间差计算测试。

回归背景：TaskLog.to_dict() 一旦输出带偏移的 ISO 字符串，
naive 的 datetime.now() 与之相减会抛 TypeError，原先被 except 静默吞掉，
导致"超时无日志则建议重启"永不触发。
"""
from datetime import datetime, timedelta, timezone

from app.services.task.query import seconds_since_iso


def test_naive_value_compared_with_naive_reference():
    now = datetime(2026, 10, 23, 12, 0, 0)
    assert seconds_since_iso("2026-10-23T11:00:00", now=now) == 3600


def test_aware_value_does_not_raise():
    value = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert 280 < seconds_since_iso(value) < 320


def test_unparseable_value_returns_none():
    assert seconds_since_iso("not-a-time") is None
