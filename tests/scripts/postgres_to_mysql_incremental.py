"""Incrementally upsert PostgreSQL rows created or changed after a timestamp."""

import argparse
from datetime import datetime
import sys

import psycopg2
import pymysql
from psycopg2 import sql as pg_sql

from tests.scripts.migrate_models_postgres_to_mysql import configured_url, model_table_names


TABLE_NAMES = model_table_names()


def connect_postgres():
    url = configured_url(None, "PG_SOURCE_URL", "postgresql")
    return psycopg2.connect(url.render_as_string(hide_password=False))


def connect_mysql():
    url = configured_url(None, "MYSQL_TARGET_URL", "mysql")
    return pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.database,
        charset=url.query.get("charset", "utf8mb4"),
        autocommit=False,
    )


def quote_mysql(identifier):
    return "`" + identifier.replace("`", "``") + "`"


def load_catalog(postgres, table_names):
    catalog = []
    with postgres.cursor() as cursor:
        for table_name in table_names:
            cursor.execute(
                """
                SELECT ordinal_position, column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            columns = cursor.fetchall()
            if not columns:
                raise RuntimeError(f"PostgreSQL source is missing table: {table_name}")
            cursor.execute(
                """
                SELECT con.conname, con.contype,
                       array_agg(att.attname ORDER BY ord.ordinality)
                FROM pg_constraint AS con
                JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, ordinality)
                  ON TRUE
                JOIN pg_attribute AS att
                  ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
                WHERE con.conrelid = %s::regclass AND con.contype = 'p'
                GROUP BY con.conname, con.contype
                """,
                (f"public.{table_name}",),
            )
            catalog.append({
                "name": table_name,
                "columns": columns,
                "constraints": cursor.fetchall(),
            })
    return catalog


def set_auto_increment_values(mysql, tables):
    with mysql.cursor() as cursor:
        for table in tables:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = %s
                  AND extra LIKE '%%auto_increment%%'
                """,
                (table["name"],),
            )
            for (column_name,) in cursor.fetchall():
                cursor.execute(
                    f"SELECT COALESCE(MAX({quote_mysql(column_name)}), 0) "
                    f"FROM {quote_mysql(table['name'])}"
                )
                next_value = int(cursor.fetchone()[0]) + 1
                cursor.execute(
                    f"ALTER TABLE {quote_mysql(table['name'])} AUTO_INCREMENT = %s",
                    (next_value,),
                )
    mysql.commit()


def parse_since(value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--since must be ISO format, for example 2026-08-11 12:30:00"
        ) from exc
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError(
            "--since must not include a timezone; use the PostgreSQL server's local time"
        )
    return parsed


def primary_key_columns(table):
    for _, kind, columns in table["constraints"]:
        if kind == "p":
            return columns
    raise RuntimeError(f"Table {table['name']} has no primary key")


def change_filter(table):
    columns = {column[1] for column in table["columns"]}
    if "updated_at" in columns and "created_at" in columns:
        return "(\"created_at\" > %s OR \"updated_at\" > %s)", 2
    for column_name in ("created_at", "timestamp", "result_timestamp"):
        if column_name in columns:
            return f'"{column_name}" > %s', 1
    return None, 0


def source_table_exists(mysql, table_names):
    with mysql.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
            """
        )
        target_names = {row[0] for row in cursor.fetchall()}
    missing = sorted(set(table_names) - target_names)
    if missing:
        raise RuntimeError(
            "Target MySQL is missing source tables; run the full migration first: "
            + ", ".join(missing)
        )


def target_columns(mysql, table_name):
    with mysql.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table_name,),
        )
        return {row[0] for row in cursor.fetchall()}


def upsert_sql(table_name, columns, primary_keys):
    target_columns = ", ".join(quote_mysql(column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    updates = [
        f"{quote_mysql(column)} = VALUES({quote_mysql(column)})"
        for column in columns
        if column not in primary_keys
    ]
    if not updates:
        first_key = quote_mysql(primary_keys[0])
        updates = [f"{first_key} = {first_key}"]
    return (
        f"INSERT INTO {quote_mysql(table_name)} ({target_columns}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {', '.join(updates)}"
    )


def migrate_table(postgres, mysql, table, since, batch_size, dry_run):
    table_name = table["name"]
    columns = [column[1] for column in table["columns"]]
    primary_keys = primary_key_columns(table)
    predicate, parameter_count = change_filter(table)
    pg_table = pg_sql.Identifier("public", table_name)
    pg_columns = pg_sql.SQL(", ").join(pg_sql.Identifier(column) for column in columns)
    select = pg_sql.SQL("SELECT {} FROM {}").format(pg_columns, pg_table)
    count = pg_sql.SQL("SELECT COUNT(*) FROM {}").format(pg_table)
    if predicate:
        select += pg_sql.SQL(" WHERE ") + pg_sql.SQL(predicate.replace('"', ''))
        count += pg_sql.SQL(" WHERE ") + pg_sql.SQL(predicate.replace('"', ''))
        parameters = tuple(since for _ in range(parameter_count))
        mode = "incremental"
    else:
        parameters = ()
        mode = "full-upsert (table has no timestamp column)"
    select_sql = select.as_string(postgres)

    with postgres.cursor() as cursor:
        cursor.execute(count, parameters)
        selected = cursor.fetchone()[0]
    print(f"{table_name}: {mode}, {selected} source rows", flush=True)
    if dry_run or selected == 0:
        return selected

    insert_sql = upsert_sql(table_name, columns, primary_keys)
    copied = 0
    with postgres.cursor(name=f"incremental_{table_name}") as source_cursor:
        source_cursor.itersize = batch_size
        source_cursor.execute(select_sql, parameters)
        with mysql.cursor() as target_cursor:
            while True:
                rows = source_cursor.fetchmany(batch_size)
                if not rows:
                    break
                target_cursor.executemany(insert_sql, rows)
                mysql.commit()
                copied += len(rows)
                print(f"  {table_name}: upserted {copied}/{selected}", flush=True)
    return copied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--since",
        required=True,
        type=parse_since,
        help="exclusive snapshot boundary, e.g. 2026-08-11 12:30:00",
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.batch_size <= 0:
        raise RuntimeError("--batch-size must be greater than zero")

    postgres = connect_postgres()
    mysql = None
    try:
        tables = load_catalog(postgres, TABLE_NAMES)
        postgres.rollback()
        postgres.set_session(
            readonly=True,
            autocommit=False,
            isolation_level="REPEATABLE READ",
        )
        if not args.dry_run:
            mysql = connect_mysql()
            source_table_exists(mysql, [table["name"] for table in tables])
            for table in tables:
                required = {column[1] for column in table["columns"]}
                missing = required - target_columns(mysql, table["name"])
                if missing:
                    raise RuntimeError(
                        f"Target table {table['name']} is missing columns: {sorted(missing)}"
                    )

        total = 0
        for table in tables:
            total += migrate_table(
                postgres,
                mysql,
                table,
                args.since,
                args.batch_size,
                args.dry_run,
            )
        if not args.dry_run:
            set_auto_increment_values(mysql, tables)
        print(f"incremental migration completed; source rows selected: {total}")
    finally:
        postgres.close()
        if mysql is not None:
            mysql.close()


if __name__ == "__main__":
    try:
        main()
    except (Exception, psycopg2.Error) as exc:
        print(f"incremental migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
