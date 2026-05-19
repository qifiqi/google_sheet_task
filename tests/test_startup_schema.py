from sqlalchemy import inspect, text

from app.extensions import db
from app.models import ScheduledTask
from app.startup import ensure_scheduled_task_schema


def test_ensure_scheduled_task_schema_adds_lock_fields_to_legacy_table(app_factory):
    db.session.execute(text("DROP TABLE scheduled_tasks"))
    db.session.execute(
        text(
            """
            CREATE TABLE scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                cron_expression VARCHAR(100) NOT NULL,
                task_type VARCHAR(50),
                task_function VARCHAR(255) NOT NULL,
                task_params TEXT,
                is_active BOOLEAN,
                last_run_time DATETIME,
                next_run_time DATETIME,
                run_count INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    db.session.commit()

    ensure_scheduled_task_schema()

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("scheduled_tasks")}
    indexes = inspector.get_indexes("scheduled_tasks")

    assert "is_running" in columns
    assert "running_instance_id" in columns
    assert any(index.get("column_names") == ["is_running"] for index in indexes)

    db.session.add(
        ScheduledTask(
            name="legacy scheduler task",
            cron_expression="0 0 * * *",
            task_function="cleanup_completed_tasks",
        )
    )
    db.session.commit()

    assert ScheduledTask.query.count() == 1
    assert ScheduledTask.query.first().is_running is False
