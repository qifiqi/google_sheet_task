import json
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Task, TaskLog, TaskResult, TaskResultReturn, XplAnalysisJob
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_service_C5 import GoogleSheetService as C5GoogleSheetService
from app.services.return_series_service import ReturnSeriesService
from app.services.task.error_handling import (
    TASK_ERROR_MESSAGE_MAX_LENGTH,
    format_task_error_message,
    record_task_exception,
)
from app.services.task.facade import TaskManager
from app.services.task.runtime_view import TaskRuntimeViewService
from app.services.xpl_analysis_job_service import XplAnalysisJobService, XplAnalysisJobStatus
from app.services.xpl_analysis_worker import XplAnalysisWorker


def test_return_series_service_builds_columnar_payload():
    service = ReturnSeriesService()

    payload = service.build_payload(
        [
            {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
            {"stock_date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
        ],
        source_columns={"date": "D", "index_return": "K", "start_return": "O"},
        step_index=3,
    )

    assert payload["version"] == 1
    assert payload["row_count"] == 2
    assert payload["dates"] == ["2024-01-01", "2024-01-02"]
    assert payload["index_returns"] == [0.1, 0.3]
    assert payload["start_returns"] == [0.2, 0.4]
    assert payload["source_columns"] == {"date": "D", "index_return": "K", "start_return": "O"}
    assert payload["created_from_step_index"] == 3

    rows = service.load_rows(json.dumps(payload))
    assert rows == [
        {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
        {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
    ]


def test_c3_save_task_result_persists_return_series_snapshot(app_factory):
    app = app_factory
    with app.app_context():
        task_id = "c3-return-series-task"
        task = Task(
            id=task_id,
            name="c3 return series task",
            task_type="google_sheet",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        service = GoogleSheetService({}, task_id, app=app)
        service._save_task_result(
            4,
            [1, 2, 3],
            {
                "I15": 0.12,
                "flat_result": {"start_drawdown": 0.3},
                "_return_series_snapshot": {
                    "rows": [
                        {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                        {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
                    ],
                    "source_columns": {"date": "D", "index_return": "K", "start_return": "O"},
                },
            },
            True,
        )

        stored = TaskResult.query.filter_by(task_id=task_id).one()
        assert stored.return_series_id is not None

        stored_result = json.loads(stored.result)
        assert "_return_series_snapshot" not in stored_result
        assert stored_result["I15"] == 0.12
        assert stored_result["flat_result"] == {"start_drawdown": 0.3}

        series = db.session.get(TaskResultReturn, stored.return_series_id)
        payload = json.loads(series.returns_json)
        assert payload["row_count"] == 2
        assert payload["created_from_step_index"] == 4
        assert payload["source_columns"] == {"date": "D", "index_return": "K", "start_return": "O"}
        assert payload["dates"] == ["2024-01-01", "2024-01-02"]
        assert payload["index_returns"] == [0.1, 0.3]
        assert payload["start_returns"] == [0.2, 0.4]


def test_xpl_analysis_job_service_claims_and_completes_job(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(
            id="xpl-job-task",
            name="xpl job task",
            task_type="google_sheet",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps([1, 2, 3, ["2024-01-01", "2024-01-02"]]),
            result=json.dumps({"I15": 0.1, "I19": 0.05, "analysis_status": "pending"}),
            success=True,
            return_series_id=series.id,
        )
        db.session.add(result)
        db.session.commit()

        service = XplAnalysisJobService()
        first = service.create_pending_job(task.id, result.id, series.id)
        second = service.create_pending_job(task.id, result.id, series.id)

        assert first.id == second.id
        assert XplAnalysisJob.query.filter_by(task_result_id=result.id).count() == 1

        claimed = service.claim_jobs("worker-1", limit=1)
        assert [job.id for job in claimed] == [first.id]
        assert claimed[0].status == XplAnalysisJobStatus.RUNNING
        assert claimed[0].locked_by == "worker-1"

        service.mark_completed(
            first.id,
            {"start_drawdown": 0.2, "annualized_return_diff": 0.3},
            {"monthly_excess_returns": []},
            1.25,
        )

        refreshed_job = db.session.get(XplAnalysisJob, first.id)
        refreshed_result = db.session.get(TaskResult, result.id)
        payload = json.loads(refreshed_result.result)

        assert refreshed_job.status == XplAnalysisJobStatus.COMPLETED
        assert payload["analysis_status"] == XplAnalysisJobStatus.COMPLETED
        assert payload["flat_result"]["start_drawdown"] == 0.2
        assert payload["analyze_result"] == {"monthly_excess_returns": []}
        assert payload["analysis_elapsed_seconds"] == 1.25


def test_xpl_analysis_job_service_retries_then_errors(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(id="xpl-fail-task", name="xpl fail task", task_type="google_sheet", status="running", config="{}")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result=json.dumps({"analysis_status": "pending"}),
            success=True,
            return_series_id=series.id,
        )
        db.session.add(result)
        db.session.flush()
        service = XplAnalysisJobService()
        job = service.create_pending_job(task.id, result.id, series.id, max_attempts=2, commit=False)
        db.session.commit()

        service.mark_failed(job.id, RuntimeError("first failure"))
        first = db.session.get(XplAnalysisJob, job.id)
        assert first.status == XplAnalysisJobStatus.RETRYING
        assert first.attempts == 1

        service.mark_failed(job.id, RuntimeError("second failure"))
        second = db.session.get(XplAnalysisJob, job.id)
        payload = json.loads(db.session.get(TaskResult, result.id).result)

        assert second.status == XplAnalysisJobStatus.ERROR
        assert second.attempts == 2
        assert payload["analysis_status"] == XplAnalysisJobStatus.ERROR
        assert "second failure" in payload["analysis_error"]


def test_xpl_analysis_job_service_cancels_task_jobs(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(id="xpl-cancel-task", name="xpl cancel task", task_type="google_sheet", status="running", config="{}")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(task_id=task.id, step_index=0, parameters="{}", result="{}", success=True, return_series_id=series.id)
        db.session.add(result)
        db.session.flush()
        service = XplAnalysisJobService()
        job = service.create_pending_job(task.id, result.id, series.id, commit=False)
        db.session.commit()

        assert service.cancel_jobs_for_task(task.id) == 1
        assert db.session.get(XplAnalysisJob, job.id).status == XplAnalysisJobStatus.CANCELLED


def test_xpl_analysis_job_service_recovers_stale_running_jobs(app_factory):
    app = app_factory
    with app.app_context():
        task = Task(id="xpl-stale-task", name="xpl stale task", task_type="google_sheet", status="running", config="{}")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(task_id=task.id, step_index=0, parameters="{}", result="{}", success=True, return_series_id=series.id)
        db.session.add(result)
        db.session.flush()
        job = XplAnalysisJob(
            task_id=task.id,
            task_result_id=result.id,
            return_series_id=series.id,
            status=XplAnalysisJobStatus.RUNNING,
            locked_by="dead-worker",
            locked_at=datetime.now() - timedelta(seconds=600),
        )
        db.session.add(job)
        db.session.commit()

        service = XplAnalysisJobService()
        assert service.recover_stale_running(stale_after_seconds=300) == 1

        refreshed = db.session.get(XplAnalysisJob, job.id)
        assert refreshed.status == XplAnalysisJobStatus.RETRYING
        assert refreshed.locked_by is None
        assert refreshed.locked_at is None


def test_xpl_analysis_admin_apis_list_stats_and_retry(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        monkeypatch.setenv("AUTH_ENABLED", "false")
        task = Task(id="xpl-admin-task", name="xpl admin task", task_type="google_sheet", status="completed", config="{}")
        db.session.add(task)
        db.session.add(TaskResultReturn(task_id=task.id, returns_json="{}"))
        db.session.flush()
        series = TaskResultReturn.query.filter_by(task_id=task.id).one()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result=json.dumps({"analysis_status": "error", "analysis_error": "boom"}),
            success=True,
            return_series_id=series.id,
        )
        db.session.add(result)
        db.session.flush()
        job = XplAnalysisJob(
            task_id=task.id,
            task_result_id=result.id,
            return_series_id=series.id,
            status=XplAnalysisJobStatus.ERROR,
            attempts=3,
            max_attempts=3,
            error_message="boom",
        )
        db.session.add(job)
        db.session.commit()

        client = app.test_client()
        stats_response = client.get(f"/admin/api/xpl-analysis/jobs/stats?task_id={task.id}")
        assert stats_response.status_code == 200
        assert stats_response.get_json()["stats"] == {XplAnalysisJobStatus.ERROR: 1}

        list_response = client.get(f"/admin/api/xpl-analysis/jobs?task_id={task.id}&status=error")
        assert list_response.status_code == 200
        payload = list_response.get_json()
        assert payload["pagination"]["total"] == 1
        assert payload["items"][0]["id"] == job.id

        retry_response = client.post(f"/admin/api/xpl-analysis/jobs/{job.id}/retry")
        assert retry_response.status_code == 200
        assert retry_response.get_json()["job"]["status"] == XplAnalysisJobStatus.PENDING

        refreshed_result = db.session.get(TaskResult, result.id)
        result_payload = json.loads(refreshed_result.result)
        assert result_payload["analysis_status"] == XplAnalysisJobStatus.PENDING
        assert "analysis_error" not in result_payload


def test_c3_save_task_result_async_creates_xpl_job(app_factory):
    app = app_factory
    with app.app_context():
        task_id = "c3-async-xpl-task"
        task = Task(
            id=task_id,
            name="c3 async xpl task",
            task_type="google_sheet",
            status="running",
            config="{}",
        )
        db.session.add(task)
        db.session.commit()

        service = GoogleSheetService({}, task_id, app=app)
        service._save_task_result(
            2,
            [1, 2, 3],
            {
                "I15": 0.12,
                "analysis_status": "pending",
                "_return_series_snapshot": {
                    "rows": [
                        {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                    ],
                    "source_columns": {"date": "D", "index_return": "K", "start_return": "O"},
                    "_return_analysis_async": True,
                    "max_attempts": 4,
                },
            },
            True,
        )

        stored = TaskResult.query.filter_by(task_id=task_id).one()
        stored_result = json.loads(stored.result)
        job = XplAnalysisJob.query.filter_by(task_result_id=stored.id).one()

        assert stored.return_series_id is not None
        assert stored_result["analysis_status"] == "pending"
        assert job.status == XplAnalysisJobStatus.PENDING
        assert job.return_series_id == stored.return_series_id
        assert job.max_attempts == 4


def test_xpl_worker_processes_archived_return_series_inline(app_factory, tmp_path, monkeypatch):
    app = app_factory
    with app.app_context():
        task = Task(
            id="xpl-worker-archive-task",
            name="xpl worker archive task",
            task_type="google_sheet",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        series_service = ReturnSeriesService(archive_dir=tmp_path / "return_series_archives")
        return_series = series_service.create_for_task(
            task_id=task.id,
            rows=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
            source_columns={"date": "D", "index_return": "K", "start_return": "O"},
            step_index=0,
        )
        db.session.add(return_series)
        db.session.flush()
        task_result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters=json.dumps([1, 2, 3, ["2024-01-01", "2024-01-02"]]),
            result=json.dumps({"I15": 0.1, "I19": 0.05, "analysis_status": "pending"}),
            success=True,
            return_series_id=return_series.id,
        )
        db.session.add(task_result)
        db.session.flush()
        job_service = XplAnalysisJobService()
        job = job_service.create_pending_job(task.id, task_result.id, return_series.id, commit=False)
        db.session.commit()

        series_service.archive_task_series(task.id)
        claimed = job_service.claim_jobs("worker-inline", limit=1)
        assert [item.id for item in claimed] == [job.id]

        seen_rows = []
        pushed_payloads = []

        monkeypatch.setattr(
            "app.services.google_sheet_service.GoogleSheetService.send_stock_param_result_data",
            lambda _self, payload: pushed_payloads.append(payload) or {},
        )

        def fake_xpl_runner(rows):
            seen_rows.extend(rows)
            return {"start_drawdown": 0.4}, {"monthly_excess_returns": [{"year": "all"}]}

        worker = XplAnalysisWorker(
            job_service=job_service,
            return_series_service=series_service,
            xpl_runner=fake_xpl_runner,
        )

        assert worker.run_job_inline(job.id) is True
        refreshed = db.session.get(TaskResult, task_result.id)
        payload = json.loads(refreshed.result)

        assert seen_rows == [
            {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
            {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
        ]
        assert payload["analysis_status"] == XplAnalysisJobStatus.COMPLETED
        assert payload["flat_result"] == {"start_drawdown": 0.4}
        assert pushed_payloads
        assert pushed_payloads[0]["task_id"] == task.id
        assert pushed_payloads[0]["start_drawdown"] == 0.4


def test_return_series_service_archives_task_series_to_local_gzip(app_factory, tmp_path):
    app = app_factory
    with app.app_context():
        task = Task(
            id="archive-series-task",
            name="archive series task",
            task_type="google_sheet",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        service = ReturnSeriesService(archive_dir=tmp_path / "return_series_archives")
        first_series = service.create_for_task(
            task_id=task.id,
            rows=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
            source_columns={"date": "D", "index_return": "K", "start_return": "O"},
            step_index=0,
        )
        second_series = service.create_for_task(
            task_id=task.id,
            rows=[
                {"date": "2024-01-03", "index_return": 0.5, "start_return": 0.6},
            ],
            source_columns={"date": "D", "index_return": "K", "start_return": "O"},
            step_index=1,
        )
        db.session.add_all([first_series, second_series])
        db.session.commit()

        result = service.archive_task_series(task.id)

        assert result["archived"] == 2
        archive_path = tmp_path / "return_series_archives" / f"{task.id}.json.gz"
        assert archive_path.exists()
        assert result["bytes"] > 0

        refreshed = TaskResultReturn.query.filter_by(task_id=task.id).order_by(TaskResultReturn.id.asc()).all()
        pointers = [json.loads(item.returns_json) for item in refreshed]
        assert [pointer["storage"] for pointer in pointers] == ["local_gzip", "local_gzip"]
        assert [pointer["row_count"] for pointer in pointers] == [2, 1]
        assert pointers[0]["series_id"] == refreshed[0].id
        assert pointers[1]["series_id"] == refreshed[1].id

        assert service.load_rows(refreshed[0].returns_json) == [
            {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
            {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
        ]
        assert service.load_rows(refreshed[1].returns_json) == [
            {"date": "2024-01-03", "index_return": 0.5, "start_return": 0.6},
        ]


def test_runtime_view_reads_return_chart_from_archived_series(app_factory, tmp_path):
    app = app_factory
    with app.app_context():
        task = Task(
            id="runtime-archived-series-task",
            name="runtime archived series task",
            task_type="google_sheet",
            status="completed",
            config="{}",
        )
        db.session.add(task)
        series_service = ReturnSeriesService(archive_dir=tmp_path / "return_series_archives")
        return_series = series_service.create_for_task(
            task_id=task.id,
            rows=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
            source_columns={"date": "D", "index_return": "K", "start_return": "O"},
            step_index=0,
        )
        db.session.add(return_series)
        db.session.flush()
        db.session.add(TaskResult(
            task_id=task.id,
            step_index=0,
            parameters="{}",
            result=json.dumps({"I15": 0.12, "I16": 0.34, "I17": 0.56}),
            success=True,
            return_series_id=return_series.id,
        ))
        db.session.commit()

        series_service.archive_task_series(task.id)

        summary = TaskRuntimeViewService(TaskManager()).build_result_summary(task.id)

        assert summary["return_chart"] == [
            {"date": "2024-01-01", "index_return": 0.1, "strategy_return": 0.2},
            {"date": "2024-01-02", "index_return": 0.3, "strategy_return": 0.4},
        ]


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
