from unittest.mock import MagicMock

import pytest

from app.services.google_sheet_client import GoogleSheet
from app.services.google_sheet_tasks.c3 import C3Service


def make_google_sheet():
    sheet = GoogleSheet.__new__(GoogleSheet)
    sheet.worksheet = MagicMock()
    sheet.task_id = "task-1"
    sheet._ensure_worksheet = MagicMock()
    sheet._log_ctx = MagicMock(return_value="")

    def retry(operation, _description):
        return operation()

    sheet._retry_network_operation = MagicMock(side_effect=retry)
    return sheet


def test_clear_jumped_cells_batch_clears_valid_a1_refs():
    sheet = make_google_sheet()

    sheet.clear_jumped_cells(["B2", "D5", "AA10"])

    sheet._ensure_worksheet.assert_called_once()
    sheet.worksheet.batch_clear.assert_called_once_with(["B2", "D5", "AA10"])


def test_clear_jumped_cells_skips_empty_or_invalid_refs():
    sheet = make_google_sheet()

    sheet.clear_jumped_cells(["", None, 123, "not-a-cell"])

    sheet.worksheet.batch_clear.assert_not_called()


def test_update_jumped_cells_defaults_to_raw_input():
    sheet = make_google_sheet()

    sheet.update_jumped_cells({"AA2": "2026/01/01"})

    assert sheet.worksheet.update_cells.call_args.kwargs["value_input_option"] == "RAW"


def test_update_jumped_cells_forwards_user_entered_option():
    sheet = make_google_sheet()

    sheet.update_jumped_cells({"AA2": "2026/01/01"}, value_input_option="USER_ENTERED")

    cells = sheet.worksheet.update_cells.call_args.args[0]
    assert cells[0].value == "2026/01/01"
    assert sheet.worksheet.update_cells.call_args.kwargs["value_input_option"] == "USER_ENTERED"


def make_service():
    service = C3Service({}, "task-1")
    service.google_sheet = MagicMock()
    service._log_info = MagicMock()
    service._interruptible_sleep = MagicMock(return_value=True)
    service._get_sheet_settle_seconds = MagicMock(return_value=20)
    return service


def test_write_parameter_cells_initial_attempt_only_updates():
    service = make_service()
    cell_updates = {"B2": 1, "D5": 2}

    service._write_parameter_cells(cell_updates, attempt=0)

    service.google_sheet.update_jumped_cells.assert_called_once_with(cell_updates)
    service.google_sheet.clear_jumped_cells.assert_not_called()
    service._interruptible_sleep.assert_not_called()


def test_write_parameter_cells_retry_clears_waits_then_updates():
    service = make_service()
    cell_updates = {"B2": 1, "D5": 2}

    service._write_parameter_cells(cell_updates, attempt=1)

    service.google_sheet.clear_jumped_cells.assert_called_once()
    assert list(service.google_sheet.clear_jumped_cells.call_args.args[0]) == ["B2", "D5"]
    service._interruptible_sleep.assert_called_once_with(20)
    service.google_sheet.update_jumped_cells.assert_called_once_with(cell_updates)


def test_write_parameter_cells_retry_uses_configured_wait():
    service = make_service()
    service._get_sheet_settle_seconds = MagicMock(return_value=7)

    service._write_parameter_cells({"B2": 1}, attempt=1)

    service._interruptible_sleep.assert_called_once_with(7)


def test_write_parameter_cells_retry_raises_when_cancelled_during_wait():
    service = make_service()
    service._interruptible_sleep.return_value = False
    cell_updates = {"B2": 1}

    with pytest.raises(RuntimeError, match="task cancelled"):
        service._write_parameter_cells(cell_updates, attempt=1)

    service.google_sheet.clear_jumped_cells.assert_called_once()
    service.google_sheet.update_jumped_cells.assert_not_called()
