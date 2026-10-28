from unittest.mock import MagicMock

from app.services.google_sheet_tasks.base import (
    DEFAULT_EXECUTION_DELAY_MAX,
    DEFAULT_EXECUTION_DELAY_MIN,
    DEFAULT_SHEET_REFRESH_ATTEMPTS,
    DEFAULT_SHEET_REFRESH_INTERVAL,
    DEFAULT_SHEET_SETTLE_SECONDS,
    BaseGoogleSheetService,
)


class FakeConfigManager:
    def __init__(self, values):
        self.values = values

    def get_config(self, key, default=None):
        return self.values.get(key, default)


def make_service(monkeypatch, values):
    service = BaseGoogleSheetService({}, "task-1")
    service._log_warning = MagicMock()
    monkeypatch.setattr(
        "app.services.google_sheet_tasks.base.get_config_manager",
        lambda: FakeConfigManager(values),
    )
    return service


def test_execution_poll_delay_increases_until_max():
    delays = [
        BaseGoogleSheetService._get_execution_poll_delay(attempt, 20, 30)
        for attempt in range(5)
    ]

    assert delays == [20, 25, 30, 30, 30]


def test_execution_poll_delay_bounds_read_config_once(monkeypatch):
    service = make_service(
        monkeypatch,
        {
            "execution_delay_min": "10",
            "execution_delay_max": "25",
        },
    )

    assert service._get_execution_poll_delay_bounds() == (10, 25)
    service._log_warning.assert_not_called()


def test_execution_poll_delay_bounds_fallback_for_invalid_config(monkeypatch):
    service = make_service(
        monkeypatch,
        {
            "execution_delay_min": "40",
            "execution_delay_max": "30",
        },
    )

    assert service._get_execution_poll_delay_bounds() == (
        DEFAULT_EXECUTION_DELAY_MIN,
        DEFAULT_EXECUTION_DELAY_MAX,
    )
    service._log_warning.assert_called_once()


def test_sheet_settle_seconds_reads_config(monkeypatch):
    service = make_service(monkeypatch, {"sheet_settle_seconds": "35"})

    assert service._get_sheet_settle_seconds() == 35
    service._log_warning.assert_not_called()


def test_sheet_settle_seconds_fallback_for_invalid_config(monkeypatch):
    service = make_service(monkeypatch, {"sheet_settle_seconds": "301"})

    assert service._get_sheet_settle_seconds() == DEFAULT_SHEET_SETTLE_SECONDS
    service._log_warning.assert_called_once()


def test_poll_refresh_settings_defaults(monkeypatch):
    service = make_service(monkeypatch, {})

    assert service._get_poll_refresh_settings() == (
        DEFAULT_SHEET_REFRESH_INTERVAL,
        frozenset(DEFAULT_SHEET_REFRESH_ATTEMPTS),
    )


def test_poll_refresh_settings_reads_attempts_and_disables_interval(monkeypatch):
    service = make_service(
        monkeypatch,
        {
            "sheet_refresh_interval_attempts": "0",
            "sheet_refresh_attempts": "3, 6, 9",
        },
    )

    assert service._get_poll_refresh_settings() == (0, frozenset({3, 6, 9}))


def test_poll_refresh_settings_fallback_for_invalid_attempts(monkeypatch):
    service = make_service(
        monkeypatch,
        {
            "sheet_refresh_attempts": [0, 60],
            "sheet_refresh_interval_attempts": "not-a-number",
        },
    )

    interval, attempts = service._get_poll_refresh_settings()

    assert interval == DEFAULT_SHEET_REFRESH_INTERVAL
    assert attempts == frozenset(DEFAULT_SHEET_REFRESH_ATTEMPTS)
    assert service._log_warning.call_count == 2


def test_poll_refresh_uses_configured_attempts(monkeypatch):
    service = make_service(
        monkeypatch,
        {
            "sheet_refresh_attempts": [2],
            "sheet_refresh_interval_attempts": 0,
            "sheet_settle_seconds": "7",
        },
    )
    service._get_execution_poll_delay_bounds = lambda: (0, 0)
    service._interruptible_sleep = MagicMock(return_value=True)
    service._log_info = MagicMock()
    refresh_calls = []

    done, payload = service._poll_google_sheet_completion(
        lambda attempt: (attempt == 3, attempt),
        refresh_fn=refresh_calls.append,
    )

    assert (done, payload) == (True, 3)
    assert refresh_calls == [7]
