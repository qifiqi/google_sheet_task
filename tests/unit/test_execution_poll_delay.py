from unittest.mock import MagicMock

from app.services.google_sheet_service_base import (
    DEFAULT_EXECUTION_DELAY_MAX,
    DEFAULT_EXECUTION_DELAY_MIN,
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
        "app.services.google_sheet_service_base.get_config_manager",
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
