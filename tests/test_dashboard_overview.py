from datetime import datetime, timedelta

from app.extensions import db
from app.models import (
    BacktestSheetRunLock,
    GoogleSheet,
    GoogleSheetToken,
    ScheduledTask,
    StockMetadata,
    Task,
    TaskLog,
    TaskResult,
    TaskResultReturn,
    TaskResultSummaryIndex,
    TaskTemplate,
    XplAnalysisJob,
)
from app.services.task import TaskManager, TaskRuntimeViewService
from app.services.task.dashboard_query import TaskDashboardQueryService


class _FakeUser:
    def __init__(self, permissions):
        self._permissions = set(permissions)

    def get_permissions(self):
        return set(self._permissions)


def test_dashboard_overview_includes_permission_scoped_operational_health(app_factory):
    task = Task(
        id="dashboard-task",
        name="dashboard task",
        task_type="google_sheet",
        status="completed",
        config="{}",
        current_step=2,
        total_steps=2,
        start_time=datetime.now() - timedelta(minutes=3),
        end_time=datetime.now(),
    )
    db.session.add(task)
    db.session.flush()

    return_series = TaskResultReturn(
        task_id=task.id,
        returns_json="{}",
    )
    db.session.add(return_series)
    db.session.flush()

    successful_result = TaskResult(
        task_id=task.id,
        step_index=0,
        success=True,
        result="{}",
        return_series_id=return_series.id,
    )
    failed_result = TaskResult(
        task_id=task.id,
        step_index=1,
        success=False,
        result="{}",
        error_message="result failed",
    )
    db.session.add_all([successful_result, failed_result])
    db.session.flush()

    db.session.add_all(
        [
            XplAnalysisJob(
                task_id=task.id,
                task_result_id=successful_result.id,
                return_series_id=return_series.id,
                status="pending",
            ),
            TaskLog(
                task_id=task.id,
                level="warning",
                message="dashboard warning",
            ),
            GoogleSheet(
                name="dashboard sheet",
                spreadsheet_id="dashboard-sheet",
                table_type="c3",
                is_active=True,
                is_in_use=True,
                current_task_id=task.id,
            ),
            GoogleSheetToken(
                name="dashboard token",
                token_file="dashboard-token.json",
                token_context="{}",
                is_active=True,
                current_in_use_count=0,
                max_usage_count=1,
            ),
            ScheduledTask(
                name="dashboard schedule",
                cron_expression="0 0 * * *",
                task_function="cleanup_completed_tasks",
                is_active=True,
                is_running=False,
                next_run_time=datetime.now() + timedelta(hours=1),
            ),
            BacktestSheetRunLock(
                spreadsheet_id="dashboard-lock",
                task_id=task.id,
                task_type="backtest_training",
            ),
            TaskTemplate(name="dashboard template", config="{}"),
            StockMetadata(
                stock_code="TEST",
                stock_name="Dashboard Stock",
                market_type="cn",
            ),
            TaskResultSummaryIndex(
                task_id=task.id,
                task_result_id=successful_result.id,
                task_type="google_sheet",
                model_key="dashboard-model",
                is_best=True,
            ),
        ]
    )
    db.session.commit()

    user = _FakeUser(
        {
            "task:view",
            "google_sheet:c3",
            "google_sheet:view",
            "scheduler:view",
            "template:view",
            "backtest:view",
            "database:model_summary",
        }
    )
    overview = TaskRuntimeViewService(TaskManager()).build_dashboard_overview(user)

    assert overview["execution_health"]["results"] == {
        "total": 2,
        "success": 1,
        "failed": 1,
        "success_rate": 50.0,
    }
    assert overview["execution_health"]["xpl_jobs"]["pending"] == 1
    assert overview["execution_health"]["xpl_jobs"]["backlog"] == 1
    assert overview["resource_health"]["google_sheets"]["in_use"] == 1
    assert overview["resource_health"]["google_sheets"]["available"] == 0
    assert overview["resource_health"]["google_sheet_tokens"]["available"] == 1
    assert overview["resource_health"]["scheduled_tasks"]["active"] == 1
    assert overview["resource_health"]["backtest_locks"]["active"] == 1
    assert overview["resource_health"]["catalog"] == {
        "task_templates": 1,
        "stock_metadata": 1,
        "result_summaries": 1,
        "best_summaries": 1,
    }
    assert overview["recent_alerts"][0]["message"] == "dashboard warning"
    assert set(overview["recent_tasks"][0]) == {
        "id",
        "name",
        "task_type",
        "status",
        "current_step",
        "total_steps",
        "progress_percentage",
        "duration_seconds",
        "error_message",
        "start_time",
        "end_time",
        "created_at",
    }


def test_dashboard_overview_hides_resource_health_without_resource_permissions(app_factory):
    db.session.add(
        Task(
            id="dashboard-limited-task",
            name="limited task",
            task_type="google_sheet",
            status="pending",
            config="{}",
            current_step=0,
            total_steps=1,
        )
    )
    db.session.commit()

    overview = TaskRuntimeViewService(TaskManager()).build_dashboard_overview(
        _FakeUser({"task:view", "google_sheet:c3"})
    )

    assert overview["resource_health"] == {}


def test_dashboard_period_aggregates_task_and_result_activity(app_factory):
    now = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    completed_task = Task(
        id="period-completed",
        name="period completed",
        task_type="google_sheet",
        status="completed",
        config="{}",
        created_at=now - timedelta(days=2),
        end_time=now - timedelta(days=1),
    )
    unauthorized_task = Task(
        id="period-unauthorized",
        name="period unauthorized",
        task_type="google_sheet_c4",
        status="error",
        config="{}",
        created_at=now - timedelta(days=1),
        end_time=now,
    )
    db.session.add_all([completed_task, unauthorized_task])
    db.session.flush()
    db.session.add_all([
        TaskResult(
            task_id=completed_task.id,
            step_index=0,
            success=True,
            timestamp=now - timedelta(days=1),
        ),
        TaskResult(
            task_id=completed_task.id,
            step_index=1,
            success=False,
            timestamp=now,
        ),
        TaskResult(
            task_id=unauthorized_task.id,
            step_index=0,
            success=False,
            timestamp=now,
        ),
    ])
    db.session.commit()

    period = TaskDashboardQueryService().get_period_overview(
        ["google_sheet"],
        now,
        days=7,
    )

    task_trend = {item["date"]: item for item in period["task_trend"]}
    result_trend = {item["date"]: item for item in period["result_trend"]}
    assert period["days"] == 7
    assert len(period["task_trend"]) == 7
    assert len(period["result_trend"]) == 7
    assert task_trend[(now - timedelta(days=2)).date().isoformat()]["created"] == 1
    assert task_trend[(now - timedelta(days=1)).date().isoformat()]["completed"] == 1
    assert task_trend[now.date().isoformat()]["error"] == 0
    assert result_trend[(now - timedelta(days=1)).date().isoformat()]["success"] == 1
    assert result_trend[now.date().isoformat()]["failed"] == 1
    assert period["task_type_status_distribution"] == [
        {"task_type": "google_sheet", "status": "completed", "count": 1}
    ]
