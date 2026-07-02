import json

from app.extensions import db
from app.models import Task, TaskResult
from app.routes.backtest_training import _extract_task_result_payload
from app.services.backtest_parameter_utils import normalize_c3_parameter_row
from app.services.backtest_training_service import BacktestTrainingService
from app.services.task.facade import TaskManager


def test_extract_task_result_payload_handles_metadata_outside_sheet_payload(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="bt-result-meta",
            name="bt-result-meta",
            task_type="backtest_training",
            status="completed",
        )
        db.session.add(task)
        task_result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result=json.dumps({
                "return_series_id": 99,
                "sheet__title": {
                    "calculate_metrics": {
                        "excess_returns": [
                            {
                                "year": "all",
                                "start_annualized_return": 0.12,
                            }
                        ]
                    },
                    "D2": "12%",
                },
            }),
            success=True,
        )
        db.session.add(task_result)
        db.session.commit()

        calculate_metrics, sheet_result = _extract_task_result_payload(task_result)

        assert calculate_metrics["excess_returns"][0]["start_annualized_return"] == 0.12
        assert sheet_result["D2"] == "12%"


def test_backtest_save_task_result_stores_returns_in_return_table_only(app_factory):
    app = app_factory
    with app.app_context():
        service = BacktestTrainingService({}, "bt-save-task")
        task = Task(
            id="bt-save-task",
            name="bt-save-task",
            task_type="backtest_training",
            status="running",
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

        service._save_task_result(
            0,
            {"stock_code": "TEST"},
            {
                "sheet__title": {
                    "calculate_metrics": {
                        "excess_returns": [
                            {"year": "all", "start_annualized_return": 0.2}
                        ]
                    },
                    "D2": "20%",
                }
            },
            True,
            return_date=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
        )

        stored = TaskResult.query.filter_by(task_id=task_id).one()
        payload = json.loads(stored.result)

        assert "_return_date" not in json.dumps(payload, ensure_ascii=False)
        assert stored.return_series_id is not None


def test_backtest_training_keeps_price_mode_in_config(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()

        normalized_default = manager._normalize_task_config_for_type("backtest_training", {
            "sheet": {"spreadsheet_id": "sheet-1"},
        })
        normalized_custom = manager._normalize_task_config_for_type("backtest_training", {
            "sheet": {"spreadsheet_id": "sheet-1"},
            "price_mode": "kp_price",
        })

        assert normalized_default["price_mode"] == "sp_price"
        assert normalized_custom["price_mode"] == "kp_price"


def test_c3_six_business_parameters_derives_second_protection():
    assert normalize_c3_parameter_row(["4", "0.8", "1", "0", "0.6", "0.4"]) == [
        "0.0350%",
        "4",
        "0.8",
        "1.2",
        "1",
        "0",
        "0.6",
        "0.4",
    ]


def test_backtest_training_normalizes_six_parameter_rows_on_create(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()

        normalized = manager._normalize_task_config_for_type("backtest_training", {
            "sheet": {"spreadsheet_id": "sheet-1", "title": "C3"},
            "parameters": [["4", "0.8", "1", "0", "0.6", "0.4"]],
        })

        assert normalized["parameters"] == [[
            "0.0350%",
            "4",
            "0.8",
            "1.2",
            "1",
            "0",
            "0.6",
            "0.4",
        ]]


def test_backtest_training_preserves_complete_c3_parameter_rows(app_factory):
    app = app_factory
    with app.app_context():
        manager = TaskManager()
        complete_row = ["0.02%", "4", "0.8", "1.1", "1", "0", "0.6", "0.4"]

        normalized = manager._normalize_task_config_for_type("backtest_training", {
            "sheet": {"spreadsheet_id": "sheet-1", "title": "C3"},
            "parameters": [complete_row],
        })

        assert normalized["parameters"] == [complete_row]
