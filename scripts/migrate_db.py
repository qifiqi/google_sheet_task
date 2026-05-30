#!/usr/bin/env python3
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert


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
DEFAULT_TARGET_DB = "postgresql://validator_user:validator_password@127.0.0.1:5432/googlesheet_validator"
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
TASK_CHILD_TABLES = {
    "task_logs",
    "task_result_summary_index",
    "task_results",
    "task_results_return",
}


def reset_postgres_sequence(conn, table):
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        return

    pk_column = pk_columns[0]
    python_type = getattr(pk_column.type, "python_type", None)
    if python_type is not int:
        return

    sequence_name = conn.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": table.name, "column_name": pk_column.name},
    ).scalar()

    if not sequence_name:
        return

    max_id = conn.execute(select(func.max(pk_column))).scalar()
    next_value = 1 if max_id is None else max_id
    conn.execute(
        text("SELECT setval(:sequence_name, :next_value, :is_called)"),
        {
            "sequence_name": sequence_name,
            "next_value": next_value,
            "is_called": max_id is not None,
        },
    )


def sort_tables_for_migration(source_tables):
    order_map = {name: index for index, name in enumerate(TABLE_MIGRATION_ORDER)}
    return sorted(
        source_tables,
        key=lambda table: (order_map.get(table.name, len(order_map)), table.name),
    )


def load_source_task_ids(source_conn, source_metadata):
    task_table = source_metadata.tables.get("tasks")
    if task_table is None:
        return set()
    return set(source_conn.execute(select(task_table.c.id)).scalars().all())


def filter_task_child_rows(table_name, rows, valid_task_ids):
    if table_name not in TASK_CHILD_TABLES:
        return rows, 0

    filtered_rows = []
    skipped_count = 0
    for row in rows:
        if row.get("task_id") in valid_task_ids:
            filtered_rows.append(row)
        else:
            skipped_count += 1
    return filtered_rows, skipped_count


def upsert_batch(target_conn, target_table, batch, dialect_name):
    if dialect_name == "postgresql":
        primary_keys = [column.name for column in target_table.primary_key.columns]
        insert_stmt = pg_insert(target_table).values(batch)

        if primary_keys:
            update_columns = {
                column.name: insert_stmt.excluded[column.name]
                for column in target_table.columns
                if column.name not in primary_keys
            }
            if not update_columns:
                target_conn.execute(
                    insert_stmt.on_conflict_do_nothing(index_elements=primary_keys)
                )
                return

            target_conn.execute(
                insert_stmt.on_conflict_do_update(
                    index_elements=primary_keys,
                    set_=update_columns,
                )
            )
            return

        target_conn.execute(insert_stmt)
        return

    target_conn.execute(target_table.insert(), batch)


def migrate_database(
    source_url=DEFAULT_SOURCE_DB,
    target_url=DEFAULT_TARGET_DB,
    chunk_size=500,
):
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
        source_task_ids = load_source_task_ids(source_conn, source_metadata)

        for source_table in source_tables:
            target_table = target_metadata.tables[source_table.name]
            rows = source_conn.execute(select(source_table)).mappings().all()

            if not rows:
                print(f"{source_table.name}: 0 rows")
                continue

            row_dicts = [dict(row) for row in rows]
            inserted_count = 0
            skipped_count = 0

            for i in range(0, len(row_dicts), chunk_size):
                batch = row_dicts[i:i + chunk_size]
                batch, skipped_in_batch = filter_task_child_rows(
                    source_table.name,
                    batch,
                    source_task_ids,
                )
                skipped_count += skipped_in_batch

                if not batch:
                    continue

                upsert_batch(
                    target_conn,
                    target_table,
                    batch,
                    target_engine.dialect.name,
                )
                inserted_count += len(batch)

            if target_engine.dialect.name == "postgresql":
                reset_postgres_sequence(target_conn, target_table)

            if skipped_count:
                print(f"{source_table.name}: {inserted_count} rows, skipped {skipped_count} orphan rows")
            else:
                print(f"{source_table.name}: {inserted_count} rows")

    print("Migration completed.")


if __name__ == "__main__":
    migrate_database()
