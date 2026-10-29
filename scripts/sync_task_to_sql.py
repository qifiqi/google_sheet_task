"""任务同步：测试 PG -> 线上 MySQL 导入 SQL（任务/结果/收益序列/随机K线，日志不入库）。

用法：

    SOURCE_DATABASE_URL=postgresql://... \
        python scripts/sync_task_to_sql.py --task-ids <TASK_ID> -o 导入补.sql
        python scripts/sync_task_to_sql.py --since 2026-10-24 -o 导入补.sql

原理（解决两端 id 不同 + 线上持续写入）：
    - results / return / K线三表全部【不带 id】INSERT，线上 AUTO_INCREMENT 现场分配；
    - 每行插入后用 SET @变量 := LAST_INSERT_ID() 记下本连接拿到的新 id（连接级隔离，
      线上并发写入互不干扰）；
    - 引用列（results.return_series_id、series.source_id、links.result_id / series_id）
      统一引用这些 @变量，交叉关系在执行时自动成立；
    - 执行前按 task_id 删除本批任务的全部子表与主表，可重复执行覆盖旧快照；
    - t_param_tasks 保留原 UUID：UUID 全局唯一，不会与线上另行创建的任务撞主键；
      线上同名但 UUID 不同的任务不在本文件删除范围内，需另行清理。
    - 输出流式写盘，不把整份 SQL 拼进内存。

产物执行：mysql 客户端 source，或 docker exec -i 容器 mysql < 文件（同一连接内完成）。
源查询全部为内联 SQL 字面量 + 占位符绑定；凭据走环境变量。
"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2

FALLBACK_DATE = date(1970, 1, 1)

# 主表之外所有带 task_id 的表；未同步的表也要清，避免覆盖任务后留下孤儿行。
TASK_CHILD_TABLES = (
    "t_param_task_results",
    "t_param_task_results_return",
    "t_param_task_kline_sources",
    "t_param_task_random_series",
    "t_param_task_result_kline_links",
    "t_param_task_logs",
    "t_param_task_result_summary_index",
)


def sql_literal(value):
    """Python 值 -> MySQL SQL 字面量（仅用于生成给 mysql 客户端执行的产物文件）。"""
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
    return "'" + text + "'"


def rows_to_dicts(cur):
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_source(task_ids, since, source_url):
    conn = psycopg2.connect(source_url)
    try:
        with conn.cursor() as cur:
            if task_ids:
                cur.execute(
                    """
                    SELECT id, name, description, status, task_type, config,
                           created_by_user_id, start_time, end_time, current_step,
                           total_steps, error_message, created_at, updated_at
                    FROM t_param_tasks
                    WHERE id = ANY(%(ids)s)
                    """,
                    {"ids": task_ids},
                )
            else:
                cur.execute(
                    """
                    SELECT id, name, description, status, task_type, config,
                           created_by_user_id, start_time, end_time, current_step,
                           total_steps, error_message, created_at, updated_at
                    FROM t_param_tasks
                    WHERE created_at >= %(since)s
                    """,
                    {"since": since},
                )
            tasks = rows_to_dicts(cur)
            if not tasks:
                print("源库没有匹配的任务")
                sys.exit(1)
            ids = [t["id"] for t in tasks]

            cur.execute(
                """
                SELECT id, task_id, step_index, parameters, result, success,
                       error_message, timestamp, return_series_id
                FROM t_param_task_results
                WHERE task_id = ANY(%(ids)s)
                ORDER BY id
                """,
                {"ids": ids},
            )
            results = rows_to_dicts(cur)
            cur.execute(
                """
                SELECT id, task_id, stock_code, stock_name, start_return_date,
                       end_return_date, return_length, stock_date, index_return,
                       start_return, created_at
                FROM t_param_task_results_return
                WHERE task_id = ANY(%(ids)s)
                ORDER BY id
                """,
                {"ids": ids},
            )
            returns = rows_to_dicts(cur)
            cur.execute(
                """
                SELECT id, task_id, stock_code, stock_name, market_type, kline_key,
                       data_source, adjust_type, start_date, end_date, row_count,
                       dates_json, open_json, high_json, low_json, close_json,
                       vwap_json, created_at
                FROM t_param_task_kline_sources
                WHERE task_id = ANY(%(ids)s)
                ORDER BY id
                """,
                {"ids": ids},
            )
            kline_sources = rows_to_dicts(cur)
            cur.execute(
                """
                SELECT id, source_id, task_id, stock_code, kline_key, dataset_key,
                       random_group, price_mode, random_price_range, seed, row_count,
                       values_json, created_at
                FROM t_param_task_random_series
                WHERE task_id = ANY(%(ids)s)
                ORDER BY id
                """,
                {"ids": ids},
            )
            random_series = rows_to_dicts(cur)
            cur.execute(
                """
                SELECT id, result_id, task_id, series_id, created_at
                FROM t_param_task_result_kline_links
                WHERE task_id = ANY(%(ids)s)
                ORDER BY id
                """,
                {"ids": ids},
            )
            kline_links = rows_to_dicts(cur)
        return tasks, results, returns, kline_sources, random_series, kline_links
    finally:
        conn.close()


def safe_output_path(raw):
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    if ".." in path.parts:
        print(f"拒绝包含 .. 的路径：{raw}")
        sys.exit(1)
    return path


def comment_text(value, limit=200):
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-ids", nargs="*", help="要同步的任务ID（推荐）")
    parser.add_argument("--since", help="按 t_param_tasks.created_at >= 此时间批量选取")
    parser.add_argument("-o", "--output", required=True, help="输出 SQL 文件")
    args = parser.parse_args()

    source_url = os.environ.get("SOURCE_DATABASE_URL")
    if not source_url:
        print("缺少 SOURCE_DATABASE_URL 环境变量（测试 PG 连接串；凭据不入源码）")
        sys.exit(1)
    if not args.task_ids and not args.since:
        print("必须提供 --task-ids 或 --since")
        sys.exit(1)

    print("读取测试库数据 ...")
    tasks, results, returns, kline_sources, random_series, kline_links = fetch_source(
        args.task_ids, args.since, source_url
    )
    print(
        f"任务 {len(tasks)}，results {len(results)}，return {len(returns)}，"
        f"K线快照 {len(kline_sources)}，随机序列 {len(random_series)}，关联 {len(kline_links)}"
    )

    # 源 id -> 会话变量名（执行时由 LAST_INSERT_ID() 赋值）
    def var(prefix, old_id):
        return f"@{prefix}_{old_id}"

    output_path = safe_output_path(args.output)

    def emit(line):
        out.write(line)
        out.write("\n")

    id_list = ", ".join(sql_literal(t["id"]) for t in tasks)

    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        emit("SET NAMES utf8mb4;")
        emit("SET FOREIGN_KEY_CHECKS = 0;")
        emit("START TRANSACTION;")
        emit("")
        emit(f"-- 生成时间: {datetime.now().isoformat(sep=' ', timespec='seconds')}")
        emit(f"-- 任务数: {len(tasks)}（UUID 主键保留原值；子表 id 由线上自增分配）")
        for task in tasks:
            emit(f"--   {task['id']} | {comment_text(task.get('name'))}")
        emit("")

        # 先清本批任务的全部子表，再清主表，最后重新插入，保证可重复执行。
        for table in TASK_CHILD_TABLES:
            emit(f"DELETE FROM {table} WHERE task_id IN ({id_list});")
        emit(f"DELETE FROM t_param_tasks WHERE id IN ({id_list});")
        emit("")

        # 1. 主表：UUID 主键保留原值
        task_columns = [
            "id", "name", "description", "status", "task_type", "config",
            "created_by_user_id", "start_time", "end_time", "current_step",
            "total_steps", "error_message", "created_at", "updated_at",
        ]
        emit("-- 任务主表")
        for task in tasks:
            values = [sql_literal(task.get(col)) for col in task_columns]
            emit(
                "INSERT INTO t_param_tasks (" + ", ".join(task_columns) + ") "
                f"VALUES ({', '.join(values)});"
            )
        emit("")

        # 2. 收益序列：不带 id 插入，记录 LAST_INSERT_ID
        emit("-- 收益序列（自增现场分配，@r_<源id> = 新id）")
        for ret in returns:
            cols = ["task_id", "stock_code", "stock_name", "start_return_date",
                    "end_return_date", "return_length", "stock_date", "index_return",
                    "start_return", "created_at"]
            values = [sql_literal(ret.get("task_id")), sql_literal(ret.get("stock_code")),
                      sql_literal(ret.get("stock_name"))]
            for col in ("start_return_date", "end_return_date"):
                value = ret.get(col)
                values.append(sql_literal(FALLBACK_DATE if value is None else value))
            for col in ("return_length", "stock_date", "index_return", "start_return", "created_at"):
                values.append(sql_literal(ret.get(col)))
            emit(
                "INSERT INTO t_param_task_results_return (" + ", ".join(cols) + ") "
                f"VALUES ({', '.join(values)});"
            )
            emit(f"SET {var('r', ret['id'])} = LAST_INSERT_ID();")
        emit("")

        # 3. results：return_series_id 引用 @r_*
        emit("-- results（return_series_id 引用会话变量）")
        for res in results:
            old_series = res.get("return_series_id")
            series_ref = var("r", old_series) if old_series else "NULL"
            emit(
                "INSERT INTO t_param_task_results "
                "(task_id, step_index, parameters, result, success, error_message, "
                "timestamp, return_series_id) "
                f"VALUES ({sql_literal(res.get('task_id'))}, {sql_literal(res.get('step_index'))}, "
                f"{sql_literal(res.get('parameters'))}, {sql_literal(res.get('result'))}, "
                f"{sql_literal(res.get('success'))}, {sql_literal(res.get('error_message'))}, "
                f"{sql_literal(res.get('timestamp'))}, {series_ref});"
            )
            emit(f"SET {var('s', res['id'])} = LAST_INSERT_ID();")
        emit("")

        # 4. K线源快照
        emit("-- 随机K线源快照")
        for source in kline_sources:
            cols = ["task_id", "stock_code", "stock_name", "market_type", "kline_key",
                    "data_source", "adjust_type", "start_date", "end_date", "row_count",
                    "dates_json", "open_json", "high_json", "low_json", "close_json",
                    "vwap_json", "created_at"]
            values = [sql_literal(source.get(c)) for c in cols]
            emit(
                "INSERT INTO t_param_task_kline_sources (" + ", ".join(cols) + ") "
                f"VALUES ({', '.join(values)});"
            )
            emit(f"SET {var('k', source['id'])} = LAST_INSERT_ID();")
        emit("")

        # 5. 随机序列：source_id 引用 @k_*；源快照缺失的孤儿行跳过（NOT NULL 列无法安全落库）
        emit("-- 随机序列（source_id 引用快照变量）")
        fetched_source_ids = {s["id"] for s in kline_sources}
        skipped_series = 0
        for series in random_series:
            if series.get("source_id") and series["source_id"] not in fetched_source_ids:
                skipped_series += 1
                continue
            source_ref = var("k", series["source_id"]) if series.get("source_id") else "NULL"
            emit(
                "INSERT INTO t_param_task_random_series "
                "(source_id, task_id, stock_code, kline_key, dataset_key, random_group, "
                "price_mode, random_price_range, seed, row_count, values_json, created_at) "
                f"VALUES ({source_ref}, {sql_literal(series.get('task_id'))}, "
                f"{sql_literal(series.get('stock_code'))}, {sql_literal(series.get('kline_key'))}, "
                f"{sql_literal(series.get('dataset_key'))}, {sql_literal(series.get('random_group'))}, "
                f"{sql_literal(series.get('price_mode'))}, {sql_literal(series.get('random_price_range'))}, "
                f"{sql_literal(series.get('seed'))}, {sql_literal(series.get('row_count'))}, "
                f"{sql_literal(series.get('values_json'))}, {sql_literal(series.get('created_at'))});"
            )
            emit(f"SET {var('rs', series['id'])} = LAST_INSERT_ID();")
        emit("")

        # 6. 结果-序列关联：result_id / series_id 双引用；孤儿行（任一引用缺失）跳过
        emit("-- 结果-序列关联（双引用）")
        fetched_result_ids = {r["id"] for r in results}
        fetched_series_ids = {s["id"] for s in random_series}
        skipped_links = 0
        for link in kline_links:
            if link.get("result_id") and link["result_id"] not in fetched_result_ids:
                skipped_links += 1
                continue
            if link.get("series_id") and link["series_id"] not in fetched_series_ids:
                skipped_links += 1
                continue
            result_ref = var("s", link["result_id"]) if link.get("result_id") else "NULL"
            series_ref = var("rs", link["series_id"]) if link.get("series_id") else "NULL"
            emit(
                "INSERT INTO t_param_task_result_kline_links "
                "(result_id, task_id, series_id, created_at) "
                f"VALUES ({result_ref}, {sql_literal(link.get('task_id'))}, "
                f"{series_ref}, {sql_literal(link.get('created_at'))});"
            )
        if skipped_series or skipped_links:
            print(f"警告：跳过孤儿随机序列 {skipped_series} 行、孤儿关联 {skipped_links} 行"
                  "（测试库中被引用的源行已不存在，与 50 条孤儿 return 同类现象）")

        emit("")
        emit("COMMIT;")
        emit("SET FOREIGN_KEY_CHECKS = 1;")

    print(f"生成 {output_path}（{output_path.stat().st_size / 1024 / 1024:.1f} MB）")
    print("说明：子表 id 全部由线上自增现场分配；执行前按 task_id 清旧记录，可重复执行。")
    print("注意：线上另行创建的同名任务 UUID 不同，不在本文件删除范围内。")


if __name__ == "__main__":
    main()
