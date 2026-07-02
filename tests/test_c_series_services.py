import json

from app.extensions import db
from app.models import Task, TaskLog
from app.services.google_sheet_service_C5 import GoogleSheetService as C5GoogleSheetService
from app.services.task.error_handling import (
    TASK_ERROR_MESSAGE_MAX_LENGTH,
    format_task_error_message,
    record_task_exception,
)
from app.services.task.facade import TaskManager


def test_record_task_exception_stores_trace_id_summary_and_full_log(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="trace-task",
            name="trace task",
            task_type="google_sheet_C5",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        try:
            raise ValueError("bad cell")
        except ValueError as exc:
            record = record_task_exception(task.id, exc, "unit_phase")

        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "error"
        assert refreshed.error_message == format_task_error_message(record)
        assert refreshed.error_message.startswith("trace_id=")
        assert "ValueError: bad cell" in refreshed.error_message
        assert "Traceback" not in refreshed.error_message

        log = TaskLog.query.filter_by(task_id=task.id, level="error").first()
        assert log is not None
        assert f"trace_id={record.trace_id}" in log.message
        assert "phase=unit_phase" in log.message
        assert "Traceback" in log.message


def test_record_task_exception_truncates_summary_but_keeps_full_log(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="long-error-task",
            name="long error task",
            task_type="google_sheet_C5",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        long_message = f"first line\n{'x' * 1000}"
        try:
            raise RuntimeError(long_message)
        except RuntimeError as exc:
            record = record_task_exception(task.id, exc, "unit_phase")

        refreshed = db.session.get(Task, task.id)
        assert refreshed.error_message == format_task_error_message(record)
        assert "\n" not in refreshed.error_message
        assert len(record.message) == TASK_ERROR_MESSAGE_MAX_LENGTH
        assert record.message.endswith("...")

        log = TaskLog.query.filter_by(task_id=task.id, level="error").first()
        assert log is not None
        assert "x" * 1000 in log.message


def test_record_task_exception_reuses_trace_id_and_avoids_duplicate_tasklog(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="reuse-trace-task",
            name="reuse trace task",
            task_type="google_sheet_C5",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        try:
            raise RuntimeError("same failure")
        except RuntimeError as exc:
            inner_record = record_task_exception(
                task.id,
                exc,
                "execute_parameter_combination",
                mark_error=False,
            )
            outer_record = record_task_exception(task.id, exc, "get_bdl")

        refreshed = db.session.get(Task, task.id)
        assert outer_record.trace_id == inner_record.trace_id
        assert refreshed.error_message == format_task_error_message(inner_record)
        assert TaskLog.query.filter_by(task_id=task.id, level="error").count() == 1


def test_record_task_exception_does_not_raise_when_db_write_fails(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = Task(
            id="db-failure-task",
            name="db failure task",
            task_type="google_sheet_C5",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        def fail_commit():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(db.session, "commit", fail_commit)

        try:
            raise ValueError("still return record")
        except ValueError as exc:
            record = record_task_exception(task.id, exc, "unit_phase")

        assert record.trace_id
        assert record.exception_type == "ValueError"


def test_c31_batch_create_transfers_market_end_date_and_adjustment(app_factory, monkeypatch):
    app = app_factory
    created_configs = []

    with app.app_context():
        manager = TaskManager()

        def fake_create_task(name, description, task_type, config, created_by_user_id=None):
            task_id = f"child-{len(created_configs) + 1}"
            created_configs.append(config)
            db.session.add(Task(
                id=task_id,
                name=name,
                description=description,
                task_type=task_type,
                status="pending",
                config=json.dumps(config, ensure_ascii=False),
            ))
            db.session.commit()
            return task_id

        monkeypatch.setattr(manager, "create_task", fake_create_task)
        monkeypatch.setattr(manager, "start_task", lambda _task_id: True)
        monkeypatch.setattr("app.services.task.creation.time.sleep", lambda _seconds: None)

        response, status = manager.batch_create_and_start_task({
            "name": "批量任务",
            "config": {
                "base_task_name": "批量任务",
                "market_type": "en",
                "end_date": "2026-06-30",
                "kline_adjustment": "back",
                "stock_codes": ["AAPL"],
                "parameters": [[["p1"], ["p2"]]],
                "sheets": [
                    {"spreadsheet_id": "sheet-1", "sheet_name": "data", "title": "策略-1y-1]"},
                    {"spreadsheet_id": "sheet-2", "sheet_name": "data", "title": "策略-1y-2]"},
                ],
            },
        })

        assert status == 200
        assert response["total_created"] == 2
        assert [config["market_type"] for config in created_configs] == ["en", "en"]
        assert [config["end_date"] for config in created_configs] == ["2026-06-30", "2026-06-30"]
        assert [config["kline_adjustment"] for config in created_configs] == ["back", "back"]
        assert created_configs[0]["stock_code"] == "AAPL"


def test_c31_batch_create_rejects_unaligned_sheet_count():
    manager = TaskManager()

    try:
        manager.batch_create_and_start_task({
            "name": "bad",
            "config": {
                "base_task_name": "bad",
                "stock_codes": ["600000"],
                "parameters": [[["p1"], ["p2"], ["p3"]]],
                "sheets": [
                    {"spreadsheet_id": "sheet-1", "sheet_name": "data", "title": "策略-1y-1]"},
                    {"spreadsheet_id": "sheet-2", "sheet_name": "data", "title": "策略-1y-2]"},
                ],
            },
        })
    except ValueError as exc:
        assert "参数组合数" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_c5_same_kline_source_only_writes_parameters_on_second_combination(monkeypatch):
    service = C5GoogleSheetService({}, "task-id")

    class Sheet:
        title = "sheet"
        spreadsheet_id = "spreadsheet"

        def __init__(self):
            self.clear_calls = []
            self.update_payloads = []
            self.range_reads = 0

        def clear_range(self, range_a1):
            self.clear_calls.append(range_a1)

        def get_range(self, range_a1):
            self.range_reads += 1
            if self.range_reads == 1:
                return {"D2": "0", "D3": "0"}
            return {"D2": "1", "D3": "2"}

        def get_ranges(self, ranges):
            return {
                "E2:E3": {"E2": "3", "E3": "4"},
                "J2:L3": {"J2": "0.1", "J3": "0.2", "L2": "0.3", "L3": "0.4"},
            }

        def update_jumped_cells(self, payload):
            self.update_payloads.append(dict(payload))

    sheet = Sheet()
    service.google_sheets = [sheet]
    service.xpl = type("XPL", (), {"get_return_analysis_v1": lambda self, rows: ({}, {})})()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)

    config = {
        "c5_input_column_a": "A",
        "c5_input_column_b": "B",
        "c5_output_range_1": "D2:D3",
        "c5_output_range_2": "E2:E3",
        "c5_parameter_positions": ["A1", "B1"],
        "c5_output_column_j": "J",
        "c5_output_column_l": "L",
        "market_type": "cn",
    }
    kline_map = {
        "2026-2025": [
            {"stock_date": "2025-01-01", "stock_val": 10},
            {"stock_date": "2025-01-02", "stock_val": 11},
        ]
    }
    cache = {"combination": {"Kline_key": "2026-2025"}}

    success, _result = service._execute_parameter_combination(
        10,
        {"A1": "1", "B1": "2", "stock_code": "600000", "Kline_key": "2026-2025"},
        cache,
        config,
        kline_map,
    )

    assert success is True
    assert sheet.clear_calls == []
    assert "A2" not in sheet.update_payloads[0]
    assert sheet.update_payloads[0]["A1"] == "xm:1"


def test_c5_parameter_combination_exception_records_trace_id(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        task = Task(
            id="c5-error-task",
            name="c5 error task",
            task_type="google_sheet_C5",
            status="running",
            current_step=1,
            config=json.dumps({
                "c5_input_column_a": "A",
                "c5_input_column_b": "B",
            }),
        )
        db.session.add(task)
        db.session.commit()

        service = C5GoogleSheetService({}, task.id, app=app)

        class BrokenSheet:
            title = "sheet"
            spreadsheet_id = "spreadsheet"

            def get_last_row(self, _column):
                return 0

        service.google_sheets = [BrokenSheet()]
        monkeypatch.setattr(
            service,
            "_get_all_parameters",
            lambda *_args, **_kwargs: (
                [{"stock_code": "600000", "Kline_key": "2026-2025"}],
                10,
                {
                    "2026-2025": [
                        {"stock_date": "2025-01-01", "stock_val": 10},
                        {"stock_date": "2025-01-02", "stock_val": 11},
                    ],
                },
            ),
        )
        monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)
        monkeypatch.setattr(
            service,
            "_execute_parameter_combination",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("sheet write failed")),
        )

        success_count, failed_count, status = service.get_bdl(
            task,
            task.name,
            [[["outer"]]],
            {
                "c5_input_column_a": "A",
                "c5_input_column_b": "B",
                "market_type": "cn",
            },
        )

        refreshed = db.session.get(Task, task.id)
        assert (success_count, failed_count, status) == (0, 1, "error")
        assert refreshed.status == "error"
        assert refreshed.error_message.startswith("trace_id=")
        assert "RuntimeError: sheet write failed" in refreshed.error_message
        assert "Traceback" not in refreshed.error_message

        log = TaskLog.query.filter(
            TaskLog.task_id == task.id,
            TaskLog.level == "error",
            TaskLog.message.contains("RuntimeError: sheet write failed"),
        ).first()
        assert log is not None
        assert "trace_id=" in log.message
        assert "phase=execute_parameter_combination" in log.message
        assert "RuntimeError: sheet write failed" in log.message
        assert "Traceback" in log.message


def test_runtime_cancelled_result_does_not_mark_error(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="runtime-cancelled-task",
            name="runtime cancelled task",
            task_type="google_sheet",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        manager = TaskManager()

        class TaskLogger:
            def info(self, *_args, **_kwargs):
                pass

            def warning(self, *_args, **_kwargs):
                pass

        manager._finalize_task_execution(
            task.id,
            app,
            TaskLogger(),
            "cancelled",
        )

        refreshed = db.session.get(Task, task.id)
        assert refreshed.status == "cancelled"
        assert refreshed.error_message is None
        assert TaskLog.query.filter_by(task_id=task.id, level="error").count() == 0
