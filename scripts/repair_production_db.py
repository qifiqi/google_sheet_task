#!/usr/bin/env python3
"""
Repair production database schema for additive model changes.

This script is intentionally independent from app startup. It loads the target
env file first, then patches missing columns/indexes directly against the
database so production can be repaired even when the Flask app cannot boot.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_HEAD = "20260402_add_token_task_type"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def parse_args():
    parser = argparse.ArgumentParser(description="Repair production database schema.")
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env.production"),
        help="Path to the env file used to connect to the target database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without executing them.",
    )
    return parser.parse_args()


def load_environment(env_file: str):
    env_path = Path(env_file).expanduser()
    if not env_path.is_absolute():
        env_path = (PROJECT_ROOT / env_path).resolve()

    if not env_path.exists():
        raise FileNotFoundError(f"Env file not found: {env_path}")

    load_dotenv(env_path, override=True)
    return env_path


def quote_default(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def has_index(inspector, table_name: str, index_name: str) -> bool:
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        return False
    return any(index.get("name") == index_name for index in indexes)


def has_column(inspector, table_name: str, column_name: str) -> bool:
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(column.get("name") == column_name for column in columns)


def ensure_table_type(conn, inspector, dry_run: bool, actions: list[str]):
    if not has_column(inspector, "google_sheet", "table_type"):
        actions.append("Add google_sheet.table_type")
        if not dry_run:
            conn.execute(text("ALTER TABLE google_sheet ADD COLUMN table_type VARCHAR(20)"))
            conn.execute(
                text(
                    "UPDATE google_sheet "
                    "SET table_type = 'c3' "
                    "WHERE table_type IS NULL OR TRIM(table_type) = ''"
                )
            )
            conn.execute(text("ALTER TABLE google_sheet ALTER COLUMN table_type SET DEFAULT 'c3'"))
            conn.execute(text("ALTER TABLE google_sheet ALTER COLUMN table_type SET NOT NULL"))

    if not has_index(inspector, "google_sheet", "ix_google_sheet_table_type"):
        actions.append("Create index ix_google_sheet_table_type")
        if not dry_run:
            conn.execute(
                text("CREATE INDEX ix_google_sheet_table_type ON google_sheet (table_type)")
            )


def ensure_token_columns(conn, inspector, dry_run: bool, actions: list[str]):
    if not has_column(inspector, "google_sheet_tokens", "current_in_use_count"):
        actions.append("Add google_sheet_tokens.current_in_use_count")
        if not dry_run:
            conn.execute(
                text(
                    "ALTER TABLE google_sheet_tokens "
                    "ADD COLUMN current_in_use_count INTEGER NOT NULL DEFAULT 0"
                )
            )

    if not has_column(inspector, "google_sheet_tokens", "task_type"):
        actions.append("Add google_sheet_tokens.task_type")
        if not dry_run:
            conn.execute(
                text("ALTER TABLE google_sheet_tokens ADD COLUMN task_type VARCHAR(50)")
            )
            conn.execute(
                text(
                    "UPDATE google_sheet_tokens "
                    f"SET task_type = {quote_default('google_sheet')} "
                    "WHERE task_type IS NULL OR TRIM(task_type) = ''"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE google_sheet_tokens "
                    "ALTER COLUMN task_type SET DEFAULT 'google_sheet'"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE google_sheet_tokens "
                    "ALTER COLUMN task_type SET NOT NULL"
                )
            )

    if not has_index(inspector, "google_sheet_tokens", "ix_google_sheet_tokens_task_type"):
        actions.append("Create index ix_google_sheet_tokens_task_type")
        if not dry_run:
            conn.execute(
                text(
                    "CREATE INDEX ix_google_sheet_tokens_task_type "
                    "ON google_sheet_tokens (task_type)"
                )
            )

    if not has_index(inspector, "google_sheet_tokens", "idx_google_sheet_token_active_usage"):
        actions.append("Create index idx_google_sheet_token_active_usage")
        if not dry_run:
            conn.execute(
                text(
                    "CREATE INDEX idx_google_sheet_token_active_usage "
                    "ON google_sheet_tokens (is_active, current_in_use_count)"
                )
            )


def ensure_scheduled_task_columns(conn, inspector, dry_run: bool, actions: list[str]):
    if not has_column(inspector, "scheduled_tasks", "is_running"):
        actions.append("Add scheduled_tasks.is_running")
        if not dry_run:
            conn.execute(
                text(
                    "ALTER TABLE scheduled_tasks "
                    "ADD COLUMN is_running BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )

    if not has_column(inspector, "scheduled_tasks", "running_instance_id"):
        actions.append("Add scheduled_tasks.running_instance_id")
        if not dry_run:
            conn.execute(
                text(
                    "ALTER TABLE scheduled_tasks "
                    "ADD COLUMN running_instance_id VARCHAR(100)"
                )
            )

    if not has_index(inspector, "scheduled_tasks", "idx_scheduled_tasks_is_running"):
        actions.append("Create index idx_scheduled_tasks_is_running")
        if not dry_run:
            conn.execute(
                text(
                    "CREATE INDEX idx_scheduled_tasks_is_running "
                    "ON scheduled_tasks (is_running)"
                )
            )


def ensure_alembic_version(conn, inspector, dry_run: bool, actions: list[str]):
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables:
        actions.append(f"Create alembic_version and stamp {ALEMBIC_HEAD}")
        if not dry_run:
            conn.execute(
                text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": ALEMBIC_HEAD},
            )
        return

    version_row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    current_version = version_row[0] if version_row else None
    if current_version != ALEMBIC_HEAD:
        actions.append(f"Stamp alembic_version to {ALEMBIC_HEAD}")
        if not dry_run:
            if current_version is None:
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                    {"revision": ALEMBIC_HEAD},
                )
            else:
                conn.execute(
                    text("UPDATE alembic_version SET version_num = :revision"),
                    {"revision": ALEMBIC_HEAD},
                )


def main():
    args = parse_args()
    env_path = load_environment(args.env_file)

    app = create_app()
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    masked_uri = database_uri
    if "@" in database_uri and "://" in database_uri:
        prefix, suffix = database_uri.split("://", 1)
        auth, host = suffix.rsplit("@", 1)
        if ":" in auth:
            username, _password = auth.split(":", 1)
            masked_uri = f"{prefix}://{username}:***@{host}"

    print(f"Loaded env: {env_path}")
    print(f"Target DB : {masked_uri}")

    with app.app_context():
        with db.engine.begin() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            actions: list[str] = []

            if not args.dry_run:
                db.create_all()
                inspector = inspect(conn)
                tables = set(inspector.get_table_names())
            elif not tables:
                actions.append("Create all model tables via db.create_all()")

            if "google_sheet" in tables:
                ensure_table_type(conn, inspector, args.dry_run, actions)
                inspector = inspect(conn)

            if "google_sheet_tokens" in tables:
                ensure_token_columns(conn, inspector, args.dry_run, actions)
                inspector = inspect(conn)

            if "scheduled_tasks" in tables:
                ensure_scheduled_task_columns(conn, inspector, args.dry_run, actions)
                inspector = inspect(conn)

            ensure_alembic_version(conn, inspector, args.dry_run, actions)

        if actions:
            header = "Planned operations:" if args.dry_run else "Executed operations:"
            print(header)
            for action in actions:
                print(f"- {action}")
        else:
            print("Schema already complete, nothing to do.")

    print("Done.")


if __name__ == "__main__":
    main()
