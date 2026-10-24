"""C 系列任务模型归属校验与统一 Sheet 执行锁互斥。

语义（统一 Sheet 执行锁）：
- 创建期只做合法性校验（已注册 C 系模型 + 启用），占用不再拦截创建；
- 执行互斥唯一权威是 Sheet 执行锁（键 spreadsheet_id，类型无关）；
- 启动撞锁 → queued 排队（保持 pending），持有者收尾后接力启动。
"""

from __future__ import annotations

import json

import pytest

from app.exceptions import ValidationError
from app.extensions import db
from app.models import GoogleSheet, SheetExecutionLock, Task
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


def test_create_c_series_allows_sheet_whose_other_record_is_busy(app_factory, monkeypatch):
    """占用不再拦截创建：同 spreadsheet 其他记录被占（镜像残留）也能建任务排队。"""
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

        task_id = _create_c5(manager, "shared-sheet")
        assert db.session.get(Task, task_id) is not None


def test_create_c_series_does_not_touch_occupancy_mirror(app_factory, monkeypatch):
    """创建期不再登记占用镜像：镜像只在执行期由 start_task 维护。"""
    with app_factory.app_context():
        c_series_row = _add_sheet("shared-free", "c5")
        _add_sheet("shared-free", "backtest_training")
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        _create_c5(manager, "shared-free")

        db.session.expire_all()
        c_series_row = db.session.get(GoogleSheet, c_series_row.id)
        assert c_series_row.is_in_use is False
        assert c_series_row.current_task_id is None


def test_validate_c_series_models_passes_for_registered_sheet(app_factory, monkeypatch):
    with app_factory.app_context():
        _add_sheet("own-sheet", "c5")
        _patch_token_service(monkeypatch)
        manager = TaskManager()

        task_id = _create_c5(manager, "own-sheet")
        config = json.loads(db.session.get(Task, task_id).config)

        manager.validate_c_series_sheet_models(config)


def test_start_c_series_queues_when_execution_lock_held_by_other(app_factory, monkeypatch):
    """启动时同 sheet 执行锁被其他任务持有 → queued 排队，保持 pending。"""
    with app_factory.app_context():
        sheet = _add_sheet("taken-sheet", "c5")
        _patch_token_service(monkeypatch)
        manager = TaskManager()
        task_id = _create_c5(manager, "taken-sheet")

        db.session.add(SheetExecutionLock(
            spreadsheet_id=sheet.spreadsheet_id,
            task_id="other-task",
            task_type="google_sheet_C7",
        ))
        db.session.commit()

        result = manager.start_task(task_id)
        assert result.queued
        assert "同一 Google Sheet 正在被其他任务执行" in result.message
        refreshed = db.session.get(Task, task_id)
        assert refreshed.status == "pending"
        assert refreshed.error_message.startswith("[SHEET_QUEUED]")


def test_c31_batch_with_busy_sheet_creates_queued_children(app_factory, monkeypatch):
    """C31 批量：sheet 被占不再整批拒绝，子任务创建后排队等执行锁。"""
    with app_factory.app_context():
        sheet = _add_sheet("batch-busy", "c3")
        _patch_token_service(monkeypatch)
        manager = TaskManager()
        db.session.add(SheetExecutionLock(
            spreadsheet_id=sheet.spreadsheet_id,
            task_id="other-task",
            task_type="google_sheet",
        ))
        db.session.commit()

        result = manager.batch_create_and_start_task(
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

        assert result["total_created"] == 1
        assert result["total_queued"] == 1
        assert result["total_started"] == 0
        child = Task.query.one()
        assert child.status == "pending"
        assert child.error_message.startswith("[SHEET_QUEUED]")


def test_relay_starts_pending_c_series_waiting_on_released_sheet(app_factory, monkeypatch):
    """接力泛化：C 系持有者释放 sheet 锁后，排队的同 sheet pending 任务被启动。"""
    with app_factory.app_context():
        sheet = _add_sheet("relay-sheet", "c5")
        _patch_token_service(monkeypatch)
        manager = TaskManager()
        finished_task_id = _create_c5(manager, "relay-sheet")
        waiting_task_id = _create_c5(manager, "relay-sheet")
        db.session.add(SheetExecutionLock(
            spreadsheet_id=sheet.spreadsheet_id,
            task_id=finished_task_id,
            task_type="google_sheet_C5",
        ))
        db.session.commit()

        started_calls = []

        def _fake_start(task_id):
            started_calls.append(task_id)

            class _R:
                started = True
                queued = False
                status = "started"
                message = ""

            return _R()

        monkeypatch.setattr(manager, "start_task", _fake_start)

        manager._start_next_pending_task(finished_task_id, [sheet.spreadsheet_id], None)

        assert started_calls == [waiting_task_id]
