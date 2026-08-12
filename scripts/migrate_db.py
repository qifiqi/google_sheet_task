#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.extensions import db  # noqa: E402
from app.models import (  # noqa: F401,E402
    GoogleSheetToken,
    ScheduledTask,
    SystemConfig,
    Task,
    TaskLog,
    TaskResult,
    TaskResultReturn,
    TaskTemplate,
)


DEFAULT_SOURCE_DB = f"sqlite:///{(PROJECT_ROOT / 'instance' / 'app.db').as_posix()}"
TABLE_MIGRATION_ORDER = [
    "permission",
    "role",
    "user",
    "role_permissions",
    "user_roles",
    "scheduled_tasks",
    "system_configs",
    "navigation_menu_items",
    "stock_metadata",
    "task_templates",
    "google_sheet_tokens",
    "google_sheet",
    "tasks",
    "task_results_return",
    "task_logs",
    "task_results",
    "task_result_summary_index",
]
def sort_tables_for_migration(source_tables):
    order_map = {name: index for index, name in enumerate(TABLE_MIGRATION_ORDER)}
    return sorted(
        source_tables,
        key=lambda table: (order_map.get(table.name, len(order_map)), table.name),
    )


def insert_batch(target_conn, target_table, batch):
    target_conn.execute(target_table.insert(), batch)


def migrate_database(
    source_url=DEFAULT_SOURCE_DB,
    target_url=None,
    chunk_size=500,
):
    target_url = target_url or os.environ.get("DATABASE_TARGET_URL")
    if not target_url:
        raise RuntimeError("Missing required environment variable: DATABASE_TARGET_URL")
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    db.metadata.create_all(bind=target_engine)

    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)

    target_metadata = MetaData()
    target_metadata.reflect(bind=target_engine)

    source_tables = [
        table for table in source_metadata.tables.values() if table.name in target_metadata.tables
    ]
    source_tables = sort_tables_for_migration(source_tables)

    if not source_tables:
        print("No tables found to migrate.")
        return

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        non_empty_tables = [
            target_table.name
            for source_table in source_tables
            if (
                target_table := target_metadata.tables[source_table.name]
            ) is not None
            and target_conn.scalar(select(func.count()).select_from(target_table))
        ]
        if non_empty_tables:
            raise RuntimeError(
                "Target tables must be empty for a full migration: "
                + ", ".join(non_empty_tables)
            )

        for source_table in source_tables:
            target_table = target_metadata.tables[source_table.name]
            rows = source_conn.execute(select(source_table)).mappings().all()

            if not rows:
                print(f"{source_table.name}: 0 rows")
                continue

            row_dicts = [dict(row) for row in rows]
            inserted_count = 0

            for i in range(0, len(row_dicts), chunk_size):
                batch = row_dicts[i:i + chunk_size]
                insert_batch(target_conn, target_table, batch)
                inserted_count += len(batch)

            print(f"{source_table.name}: {inserted_count} rows")

    print("Migration completed.")


if __name__ == "__main__":
    migrate_database()
