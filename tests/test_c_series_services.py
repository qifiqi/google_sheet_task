import json

from app.extensions import db
from app.models import Task
from app.services.google_sheet_service_C5 import GoogleSheetService as C5GoogleSheetService
from app.services.task.facade import TaskManager


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
