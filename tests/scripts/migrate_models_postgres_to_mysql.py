"""Restore all tables declared in app.models from PostgreSQL to an empty MySQL database."""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import Boolean, MetaData, create_engine, func, inspect, select
from sqlalchemy.engine import URL, make_url


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.extensions import db  # noqa: E402
from app.models import google_sheet_registry_scope, summary_market_type  # noqa: E402
import app.models  # noqa: F401, E402


# Keep logical parent tables ahead of task and result data. New model tables are
# appended automatically, so adding a model cannot silently exclude its data.
TABLE_ORDER = (
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
    "backtest_sheet_run_locks",
    "backtest_product_result_cache",
    "tasks",
    "task_results_return",
    "task_logs",
    "task_results",
    "task_result_summary_index",
)


def database_url(raw_url: str, expected_backend: str) -> URL:
    """Validate a connection URL without exposing its credentials in errors."""
    url = make_url(raw_url)
    if url.get_backend_name() != expected_backend:
        raise ValueError(f"Expected a {expected_backend} database URL")
    if not url.database:
        raise ValueError("Database URL must include a database name")
    if expected_backend == "mysql" and url.drivername == "mysql":
        return url.set(drivername="mysql+pymysql")
    return url


def configured_url(value: str | None, env_name: str, backend: str) -> URL:
    raw_url = value or os.environ.get(env_name)
    if not raw_url:
        raise ValueError(f"Set {env_name} or pass its command-line option")
    return database_url(raw_url, backend)


def model_table_names() -> list[str]:
    model_names = set(db.metadata.tables)
    ordered_names = [name for name in TABLE_ORDER if name in model_names]
    return ordered_names + sorted(model_names - set(ordered_names))


def row_count(connection, table) -> int:
    return connection.scalar(select(func.count()).select_from(table)) or 0


def validate_source_tables(source_metadata, table_names: list[str]) -> None:
    missing = sorted(set(table_names) - set(source_metadata.tables))
    if missing:
        raise RuntimeError("PostgreSQL is missing model tables: " + ", ".join(missing))


def target_table_names(target_engine) -> set[str]:
    return set(inspect(target_engine).get_table_names())


def _coerce_boolean(value):
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "t", "true", "y", "yes", "on"}:
            return True
        if normalized in {"0", "f", "false", "n", "no", "off"}:
            return False
    return value


def preview(source_engine, target_engine, table_names: list[str]) -> None:
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    validate_source_tables(source_metadata, table_names)
    target_names = target_table_names(target_engine)

    with source_engine.connect() as source_connection:
        with target_engine.connect() as target_connection:
            for table_name in table_names:
                source_count = row_count(source_connection, source_metadata.tables[table_name])
                target_count = (
                    row_count(target_connection, db.metadata.tables[table_name])
                    if table_name in target_names
                    else "missing"
                )
                print(f"{table_name}: PostgreSQL={source_count}, MySQL={target_count}")


def ensure_empty_target(target_engine, table_names: list[str]) -> None:
    non_empty = []
    with target_engine.connect() as connection:
        for table_name in table_names:
            count = row_count(connection, db.metadata.tables[table_name])
            if count:
                non_empty.append(f"{table_name} ({count})")
    if non_empty:
        raise RuntimeError(
            "MySQL target must be empty before a restore: " + ", ".join(non_empty)
        )


def prepare_rows(table_name: str, rows):
    target_table = db.metadata.tables[table_name]
    boolean_columns = {
        column.name
        for column in target_table.columns
        if isinstance(column.type, Boolean)
    }
    for row in rows:
        mapping = dict(row)
        for column_name in boolean_columns:
            if column_name in mapping:
                mapping[column_name] = _coerce_boolean(mapping[column_name])
        if table_name == "google_sheet" and not mapping.get("registry_scope"):
            mapping["registry_scope"] = google_sheet_registry_scope(mapping.get("table_type"))
        if table_name == "task_result_summary_index" and not mapping.get("market_type"):
            mapping["market_type"] = summary_market_type(mapping.get("stock_code"))
        yield mapping


def copy_table(source_engine, target_engine, source_table, target_table, batch_size: int) -> int:
    shared_columns = [
        source_table.c[column.name]
        for column in target_table.columns
        if column.name in source_table.c
    ]
    if not shared_columns:
        raise RuntimeError(f"No shared columns for table: {source_table.name}")

    copied = 0
    with source_engine.connect() as source_connection:
        result = source_connection.execute(
            select(*shared_columns).execution_options(stream_results=True, yield_per=batch_size)
        ).mappings()
        while rows := result.fetchmany(batch_size):
            with target_engine.begin() as target_connection:
                target_connection.execute(target_table.insert(), list(prepare_rows(target_table.name, rows)))
            copied += len(rows)
            print(f"{target_table.name}: copied {copied}", flush=True)
    return copied


def restore(source_url: URL, target_url: URL, batch_size: int, create_schema: bool, dry_run: bool) -> None:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    source_engine = create_engine(source_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    target_engine = create_engine(target_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    table_names = model_table_names()
    try:
        if dry_run:
            preview(source_engine, target_engine, table_names)
            return

        if create_schema:
            db.metadata.create_all(bind=target_engine)
        missing_target = sorted(set(table_names) - target_table_names(target_engine))
        if missing_target:
            raise RuntimeError(
                "MySQL is missing model tables; run with --create-schema: "
                + ", ".join(missing_target)
            )
        ensure_empty_target(target_engine, table_names)

        source_metadata = MetaData()
        source_metadata.reflect(bind=source_engine)
        validate_source_tables(source_metadata, table_names)
        for table_name in table_names:
            source_table = source_metadata.tables[table_name]
            target_table = db.metadata.tables[table_name]
            with source_engine.connect() as source_connection:
                source_count = row_count(source_connection, source_table)
            copied = copy_table(source_engine, target_engine, source_table, target_table, batch_size)
            with target_engine.connect() as target_connection:
                target_count = row_count(target_connection, target_table)
            if copied != source_count or target_count != source_count:
                raise RuntimeError(
                    f"Verification failed for {table_name}: source={source_count}, "
                    f"copied={copied}, target={target_count}"
                )
            print(f"{table_name}: restored {copied} rows", flush=True)
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", help="Defaults to PG_SOURCE_URL")
    parser.add_argument("--target-url", help="Defaults to MYSQL_TARGET_URL")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    restore(
        configured_url(args.source_url, "PG_SOURCE_URL", "postgresql"),
        configured_url(args.target_url, "MYSQL_TARGET_URL", "mysql"),
        args.batch_size,
        args.create_schema,
        args.dry_run,
    )


if __name__ == "__main__":
    main()
