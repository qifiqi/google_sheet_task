from datetime import datetime

import pytest

from tests.scripts.postgres_to_mysql_incremental import (
    change_filter,
    parse_since,
    upsert_sql,
)
from tests.scripts.migrate_models_postgres_to_mysql import database_url, model_table_names


def table(name, columns, constraints):
    return {
        "name": name,
        "columns": [(index, column, "text", False, "") for index, column in enumerate(columns, 1)],
        "constraints": constraints,
    }


def test_parse_since_accepts_database_local_iso_datetime():
    assert parse_since("2026-08-11 12:30:00") == datetime(2026, 8, 11, 12, 30)


def test_parse_since_rejects_timezone_to_avoid_ambiguous_boundary():
    with pytest.raises(Exception):
        parse_since("2026-08-11T12:30:00+08:00")


def test_change_filter_prefers_created_or_updated_timestamp():
    sample = table("tasks", ["id", "created_at", "updated_at"], [("pk_tasks", "p", ["id"])])
    assert change_filter(sample) == ('("created_at" > %s OR "updated_at" > %s)', 2)


def test_upsert_sql_handles_composite_primary_key_without_updates():
    statement = upsert_sql(
        "user_roles",
        ["user_id", "role_id"],
        ["user_id", "role_id"],
    )
    assert "INSERT INTO `user_roles`" in statement
    assert "ON DUPLICATE KEY UPDATE `user_id` = `user_id`" in statement


def test_full_migration_includes_tasks_and_logs():
    table_names = model_table_names()
    assert "tasks" in table_names
    assert "task_logs" in table_names


def test_migration_urls_come_from_environment(monkeypatch):
    monkeypatch.setenv(
        "PG_SOURCE_URL",
        "postgresql+psycopg2://source_user:password@127.0.0.1:5432/source_db",
    )
    monkeypatch.setenv(
        "MYSQL_TARGET_URL",
        "mysql+pymysql://target_user:password@127.0.0.1:3306/target_db?charset=utf8mb4",
    )

    assert database_url(
        "postgresql+psycopg2://source_user:password@127.0.0.1:5432/source_db",
        "postgresql",
    ).database == "source_db"
    assert database_url(
        "mysql+pymysql://target_user:password@127.0.0.1:3306/target_db?charset=utf8mb4",
        "mysql",
    ).database == "target_db"
