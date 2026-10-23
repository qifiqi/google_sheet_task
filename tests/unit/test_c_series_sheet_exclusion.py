"""C 系列任务模型归属与 Google Sheet 互斥。"""

from __future__ import annotations

import json

import pytest

from app.exceptions import ValidationError
from app.extensions import db
from app.models import GoogleSheet, Task
from app.services.task import TaskManager


def _add_sheet(spreadsheet_id: str, table_type: str, **fields) -> GoogleSheet:
    row = GoogleSheet(
        name=spreadsheet_id,
        spreadsheet_id=spreadsheet_id,
        table_type=table_type,
        **fields,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _patch_token_service(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.task.creation.get_google_sheet_token_service",
        lambda: type(
            "TokenSvc",
            (),
            {"prepare_task_config": lambda self, config: config},
        )(),
    )


def _create_c5(manager: TaskManager, spreadsheet_id: str) -> str:
    return manager.create_task(
        "c5",
        "",
        "google_sheet_C5",
        {
            "sheets": [{"spreadsheet_id": spreadsheet_id, "sheet_name": "data"}],
            "parameters": [["1"]],
        },
    )


def test_create_c_series_rejects_unregistered_sheet(app_factory, monkeypatch):
    with app_factory.app_context():
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        with pytest.raises(ValidationError, match="C 系模型"):
            _create_c5(manager, "unregistered-sheet")


def test_create_c_series_rejects_backtest_only_sheet(app_factory, monkeypatch):
    with app_factory.app_context():
        _add_sheet("backtest-only", "backtest_training")
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        with pytest.raises(ValidationError, match="C 系模型"):
            _create_c5(manager, "backtest-only")


def test_create_c_series_rejects_busy_record_of_other_type(app_factory, monkeypatch):
    with app_factory.app_context():
        _add_sheet("shared-sheet", "c5")
        _add_sheet(
            "shared-sheet",
            "backtest_training",
            is_in_use=True,
            current_task_id="other-task",
        )
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        with pytest.raises(ValidationError, match="正在被其他任务使用"):
            _create_c5(manager, "shared-sheet")


def test_create_c_series_rejects_in_use_without_current_task(app_factory, monkeypatch):
    with app_factory.app_context():
        _add_sheet("busy-null-task", "c7", is_in_use=True, current_task_id=None)
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        with pytest.raises(ValidationError, match="正在被其他任务使用"):
            _create_c5(manager, "busy-null-task")


def test_create_c_series_occupies_c_series_record_only(app_factory, monkeypatch):
    with app_factory.app_context():
        c_series_row = _add_sheet("shared-free", "c5")
        backtest_row = _add_sheet("shared-free", "backtest_training")
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        task_id = _create_c5(manager, "shared-free")

        db.session.expire_all()
        c_series_row = db.session.get(GoogleSheet, c_series_row.id)
        backtest_row = db.session.get(GoogleSheet, backtest_row.id)
        assert c_series_row.is_in_use is True
        assert c_series_row.current_task_id == task_id
        assert backtest_row.is_in_use is False
        assert backtest_row.current_task_id is None


def test_c_series_own_occupancy_is_allowed(app_factory, monkeypatch):
    with app_factory.app_context():
        _add_sheet("own-sheet", "c5")
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        task_id = _create_c5(manager, "own-sheet")
        config = json.loads(db.session.get(Task, task_id).config)

        manager.validate_c_series_sheet_models(config, task_id)


def test_start_c_series_rejects_sheet_taken_by_other_task(app_factory, monkeypatch):
    with app_factory.app_context():
        sheet = _add_sheet("taken-sheet", "c5")
        _patch_token_service(monkeypatch)
        manager = TaskManager()
        task_id = _create_c5(manager, "taken-sheet")

        sheet = db.session.get(GoogleSheet, sheet.id)
        sheet.is_in_use = True
        sheet.current_task_id = "other-task"
        db.session.commit()

        assert manager.start_task(task_id) is False
        assert "正在被其他任务使用" in manager.get_start_error(task_id)


def test_c31_batch_precheck_rejects_busy_sheet_before_creating_children(
    app_factory, monkeypatch
):
    with app_factory.app_context():
        _add_sheet(
            "batch-busy",
            "c3",
            is_in_use=True,
            current_task_id="other-task",
        )
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        with pytest.raises(ValidationError, match="正在被其他任务使用"):
            manager.batch_create_and_start_task(
                {
                    "config": {
                        "base_task_name": "batch",
                        "sheets": [
                            {
                                "spreadsheet_id": "batch-busy",
                                "sheet_name": "data",
                                "title": "策略A-1y-3]",
                            }
                        ],
                        "stock_codes": ["000001"],
                        "parameters": [["1"]],
                    }
                }
            )

        assert Task.query.count() == 0
