from datetime import datetime, timedelta

from app.extensions import db
from app.models import Task
from app.services.task.query import TaskQueryService


def test_task_statistics_average_duration_works_with_sqlite(app_factory):
    app = app_factory
    with app.app_context():
        started_at = datetime(2026, 8, 11, 14, 0, 0)
        db.session.add(
            Task(
                id="completed-task",
                name="completed",
                task_type="google_sheet_C7",
                config="{}",
                status="completed",
                start_time=started_at,
                end_time=started_at + timedelta(minutes=3),
            )
        )
        db.session.commit()

        result = TaskQueryService(task_manager=None).get_tasks_paginated(
            task_type="google_sheet_C7",
        )

        assert result["statistics"]["avg_duration_minutes"] == 3
