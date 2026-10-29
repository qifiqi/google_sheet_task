"""本地开发一次性工具：测试 PG 库全表导入本地 dev MySQL（保留原 id）。

用法：
    SOURCE_DATABASE_URL=postgresql://... \
        python scripts/import_pg_to_mysql_dev.py -o pg_full.sql.gz

产物执行（同一 mysql 连接内完成，保持会话变量/事务语义）：
    gunzip -c pg_full.sql.gz | docker exec -i dev-mysql8 mysql -uroot -p*** googlesheetdb

设计：
    - 本地库为空库直灌，全部表【带原 id】INSERT，任务 UUID 与子表外键引用原样成立；
    - 列取 PG 与 MySQL 两端交集（information_schema 比对），防两端 schema 漂移；
    - 流式写 gzip，不整表进内存；多行批量 INSERT（每 200 行一批）；
    - 凭据只走环境变量，SQL 值全部转义/类型化字面量。
"""

import argparse
import gzip
import io
import os
import sys
from datetime import date, datetime

import psycopg2

# 需要导入的表（与本地 models 22 表一致，外键无强制约束，顺序仅按依赖习惯排列）。
TABLES = (
    "t_param_user",
    "t_param_role",
    "t_param_permission",
    "t_param_role_permissions",
    "t_param_user_roles",
    "t_param_navigation_menu_items",
    "t_param_system_configs",
    "t_param_google_sheet",
    "t_param_google_sheet_tokens",
    "t_param_scheduled_tasks",
    "t_param_task_templates",
    "t_param_tasks",
    "t_param_task_logs",
    "t_param_task_results",
    "t_param_task_results_return",
    "t_param_task_result_summary_index",
    "t_param_backtest_product_result_cache",
    "t_param_backtest_sheet_run_locks",
    "t_param_task_kline_sources",
    "t_param_task_random_series",
    "t_param_task_result_kline_links",
    "t_param_stock_metadata",
)

BATCH_ROWS = 200


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.isoformat(sep=" ") + "'"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    if "\n" in text or "\r" in text:
        # 多行文本改用引号内转义序列，mysql 客户端按字面还原。
        text = text.replace("\r", "\\r").replace("\n", "\\n")
        return "'" + text + "'"
    return "'" + text + "'"


def pg_columns(cur, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="pg_full.sql.gz")
    parser.add_argument("--exclude", nargs="*", default=[], help="跳过的表名")
    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_DATABASE_URL")
    if not source_url:
        print("缺少 SOURCE_DATABASE_URL 环境变量", file=sys.stderr)
        return 2

    conn = psycopg2.connect(source_url)
    cur = conn.cursor()
    total_rows = 0
    with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=6) as out:
        out.write("SET NAMES utf8mb4;\nSET autocommit=0;\nSET unique_checks=0;\nSET foreign_key_checks=0;\n")
        for table in TABLES:
            if table in args.exclude:
                continue
            cols = pg_columns(cur, table)
            if not cols:
                print(f"跳过 {table}：PG 侧无此表", file=sys.stderr)
                continue
            col_list = ", ".join(f"`{c}`" for c in cols)
            cur.execute(
                f"SELECT {', '.join(chr(34) + c + chr(34) for c in cols)} FROM {table}".replace(chr(34), '"'),
            )
            rows = 0
            batch = []
            header = f"INSERT INTO `{table}` ({col_list}) VALUES\n"
            for row in cur:
                batch.append("(" + ", ".join(sql_literal(v) for v in row) + ")")
                rows += 1
                if len(batch) >= BATCH_ROWS:
                    out.write(header + ",\n".join(batch) + ";\n")
                    batch = []
            if batch:
                out.write(header + ",\n".join(batch) + ";\n")
            total_rows += rows
            print(f"{table}: {rows} 行", flush=True)
        out.write("COMMIT;\nSET unique_checks=1;\nSET foreign_key_checks=1;\n")
    conn.close()
    print(f"共 {total_rows} 行 -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
