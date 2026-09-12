# -*- coding: utf-8 -*-
import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from requests.adapters import HTTPAdapter


DATABASE_URL = "postgresql://postgres:Hello12345*@172.18.20.17:5432/googlesheet_validator"
API_URL = "http://stockapi.stplan.cn/api/StockParamResult/AddOrModify"

# 直接改这里
TARGET_TASK_ID = ""
START_RESULT_ID = 0
BATCH_SIZE = 2000
PRINT_PAYLOAD = False
PRINT_EVERY = 1000
DRY_RUN = False
MAX_WORKERS = 12
MAX_IN_FLIGHT = 300
CACHE_FILE = Path(__file__).with_name("sync_task_results_to_stock_param_result.cache.txt")
_thread_local = threading.local()


def build_session():
    session = requests.Session()
    session.headers.update({
        "accept": "text/plain",
        "Content-Type": "application/json-patch+json",
    })
    adapter = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_thread_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = build_session()
        _thread_local.session = session
    return session


def send_request(payload: dict):
    session = get_thread_session()
    resp = session.post(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def load_cached_task_ids():
    if not CACHE_FILE.exists():
        return set()

    task_ids = set()
    for line in CACHE_FILE.read_text(encoding="utf-8").splitlines():
        task_id = line.strip()
        if task_id:
            task_ids.add(task_id)
    return task_ids


def append_cached_task_id(task_id):
    with CACHE_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{task_id}\n")


def format_progress_bar(current, total, width=24):
    if total <= 0:
        return "[" + ("-" * width) + "]"

    ratio = min(max(current / total, 0), 1)
    filled = int(width * ratio)
    if filled >= width:
        return "[" + ("#" * width) + "]"
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def num(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return float(v)

    s = str(v).strip()
    if not s or s in {"-", "--"} or s.startswith("#"):
        return 0

    s = s.replace(",", "")
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except Exception:
            return 0

    try:
        return float(s)
    except Exception:
        return 0


def build_c3_payload(row: dict):
    task_config = json.loads(row["task_config"] or "{}")
    result_data = json.loads(row["result"] or "{}")
    parameters = json.loads(row["parameters"] or "[]")

    task_name = row.get("task_name") or ""
    stock_code = task_config.get("stock_code") or task_name.split("-", 1)[0].strip() or ""

    payload = {
        "task_id": row["task_id"],
        "stock_code": stock_code,
        "multiplier": num(result_data.get("B6") if "B6" in result_data else (parameters[0] if len(parameters) > 0 else 0)),
        "danbian": num(result_data.get("B7") if "B7" in result_data else (parameters[1] if len(parameters) > 1 else 0)),
        "xiancang": num(result_data.get("B9") if "B9" in result_data else (parameters[2] if len(parameters) > 2 else 0)),
        "zhishu": num(result_data.get("B10") if "B10" in result_data else (parameters[3] if len(parameters) > 3 else 0)),
        "smoothing": num(result_data.get("B11") if "B11" in result_data else (parameters[4] if len(parameters) > 4 else 0)),
        "bordering": num(result_data.get("B12") if "B12" in result_data else (parameters[5] if len(parameters) > 5 else 0)),
        "ml": "",
        "task_index": row["step_index"] or 0,
        "kline_range": "",
        "return_rate": num(result_data.get("I15")),
        "annualized_rate": num(result_data.get("I16")),
        "maxdd": num(result_data.get("I17")),
        "index_rate": num(result_data.get("I18")),
        "index_annualized_rate": num(result_data.get("I19")),
        "max_index_dd": num(result_data.get("I20")),
        "fee_total": num(result_data.get("I21")),
        "fee_annualized": num(result_data.get("I22")),
        "year_rate": num(result_data.get("I23")),
        "turnover_rate": 0,
        "return_beats": 0,
        "dd_beats": 0,
        "max_1y_beats": 0,
        "min_1y_beats": 0,
        "max_theoretical_leverage": 0,
        "avg_theoretical_leverage": 0,
        "unit_theoretical_leverage_return": 0,
        "max_actual_leverage": 0,
        "avg_actual_leverage": 0,
        "unit_actual_leverage_return": 0,
        "start_monthly_std_dev": 0,
        "index_monthly_std_dev": 0,
        "index_annualized_return": 0,
        "start_annualized_return": 0,
        "index_profit_annual": 0,
        "start_profit_annual": 0,
        "index_profit_monthly_percentage": 0,
        "start_profit_monthly_percentage": 0,
        "index_avg_monthly_return_common": 0,
        "start_avg_monthly_return_common": 0,
        "index_monthly_return_volatility": 0,
        "start_monthly_return_volatility": 0,
        "annualized_return_diff": 0,
        "outperform_year": 0,
        "monthly_excess_return_percentage_last_return": 0,
        "avg_monthly_excess_returns": 0,
        "monthly_excess_volatility": 0,
        "max_drawdown": 0,
        "excess_drawdown_winning_rate": 0,
        "start_drawdown": 0,
        "start_maximum_number_of_backtest_repair_days": 0,
        "excess_maximum_number_of_backtest_repair_days": 0,
        "index_sharpe_ratio": 0,
        "start_sharpe_ratio": 0,
        "index_kama_ratio": 0,
        "start_kama_ratio": 0,
        "index_sotino_ratio": 0,
        "start_sotino_ratio": 0,
        "excess_sharp": 0,
        "excess_of_promissory_note": 0,
    }
    return payload


def build_c5_payload(row: dict):
    parameters = json.loads(row["parameters"] or "{}")
    result_root = json.loads(row["result"] or "{}")
    result_data = next(iter(result_root.values()), {}) if isinstance(result_root, dict) else {}
    index_xpl = result_data.get("index_return_xpl") or {}
    start_xpl = result_data.get("start_return_xpl") or {}

    payload = {
        "task_id": row["task_id"],
        "stock_code": str(parameters.get("stock_code") or ""),
        "multiplier": str(parameters.get("A1") or ""),
        "danbian": 0,
        "xiancang": 0,
        "zhishu": 0,
        "smoothing": 0,
        "bordering": 0,
        "ml": str(parameters.get("B1") or ""),
        "task_index": row["step_index"] or 0,
        "kline_range": json.dumps(parameters.get("kline", []), ensure_ascii=False),
        "return_rate": num(result_data.get("D2")),
        "annualized_rate": num(result_data.get("D3")),
        "maxdd": num(result_data.get("D4")),
        "index_rate": num(result_data.get("D5")),
        "index_annualized_rate": num(result_data.get("D6")),
        "max_index_dd": num(result_data.get("D7")),
        "fee_total": num(result_data.get("D8")),
        "fee_annualized": num(result_data.get("D9")),
        "year_rate": 0,
        "turnover_rate": num(result_data.get("D10")),
        "return_beats": num(result_data.get("D11")),
        "dd_beats": num(result_data.get("D12")),
        "max_1y_beats": num(result_data.get("D13")),
        "min_1y_beats": num(result_data.get("D14")),
        "max_theoretical_leverage": num(result_data.get("D15")),
        "avg_theoretical_leverage": num(result_data.get("D16")),
        "unit_theoretical_leverage_return": num(result_data.get("D17")),
        "max_actual_leverage": num(result_data.get("D18")),
        "avg_actual_leverage": num(result_data.get("D19")),
        "unit_actual_leverage_return": num(result_data.get("D20")),
        "start_monthly_std_dev": num(start_xpl.get("monthly_std_dev")),
        "index_monthly_std_dev": num(index_xpl.get("monthly_std_dev")),
        "index_annualized_return": 0,
        "start_annualized_return": 0,
        "index_profit_annual": 0,
        "start_profit_annual": 0,
        "index_profit_monthly_percentage": 0,
        "start_profit_monthly_percentage": 0,
        "index_avg_monthly_return_common": num(index_xpl.get("avg_monthly_return")),
        "start_avg_monthly_return_common": num(start_xpl.get("avg_monthly_return")),
        "index_monthly_return_volatility": num(index_xpl.get("annual_std_dev")),
        "start_monthly_return_volatility": num(start_xpl.get("annual_std_dev")),
        "annualized_return_diff": 0,
        "outperform_year": 0,
        "monthly_excess_return_percentage_last_return": 0,
        "avg_monthly_excess_returns": 0,
        "monthly_excess_volatility": 0,
        "max_drawdown": 0,
        "excess_drawdown_winning_rate": 0,
        "start_drawdown": 0,
        "start_maximum_number_of_backtest_repair_days": 0,
        "excess_maximum_number_of_backtest_repair_days": 0,
        "index_sharpe_ratio": num(index_xpl.get("sharpe_ratio")),
        "start_sharpe_ratio": num(start_xpl.get("sharpe_ratio")),
        "index_kama_ratio": 0,
        "start_kama_ratio": 0,
        "index_sotino_ratio": 0,
        "start_sotino_ratio": 0,
        "excess_sharp": 0,
        "excess_of_promissory_note": 0,
    }
    return payload


def iter_task_ids(conn, target_task_id="", start_result_id=0):
    sql = """
        SELECT
            t.id,
            t.task_type,
            t.name,
            t.config,
            COALESCE(r.result_count, 0) AS result_count
        FROM tasks t
        LEFT JOIN (
            SELECT
                task_id,
                COUNT(1) AS result_count
            FROM task_results
            WHERE success = TRUE
              AND id > %s
            GROUP BY task_id
        ) r ON r.task_id = t.id
        WHERE task_type IN ('google_sheet', 'google_sheet_C5')
    """
    params = [start_result_id]

    if target_task_id:
        sql += " AND id = %s"
        params.append(target_task_id)

    sql += " ORDER BY created_at ASC, id ASC"

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def iter_task_rows(conn, task_id, start_result_id=0, batch_size=2000):
    sql = """
        SELECT
            tr.id,
            tr.task_id,
            tr.step_index,
            tr.parameters,
            tr.result,
            tr.success,
            tr.error_message,
            tr.timestamp,
            t.task_type,
            t.name AS task_name,
            t.config AS task_config
        FROM task_results tr
        JOIN tasks t ON t.id = tr.task_id
        WHERE tr.success = TRUE
          AND tr.id > %s
          AND tr.task_id = %s
          AND t.task_type IN ('google_sheet', 'google_sheet_C5')
    """
    params = [start_result_id, task_id]

    sql += " ORDER BY tr.id ASC"

    cur = conn.cursor(
        name=f"sync_task_results_stream_{task_id.replace('-', '_')[:40]}",
        cursor_factory=RealDictCursor,
    )
    cur.itersize = batch_size
    cur.execute(sql, params)

    try:
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield row
    finally:
        cur.close()


def handle_completed_futures(
    futures,
    processed,
    success_count,
    error_count,
    task_processed,
    task_success,
    task_error,
    total_results,
    last_result_id,
    start_time,
    wait_for_all=False,
):
    if not futures:
        return (
            processed,
            success_count,
            error_count,
            task_processed,
            task_success,
            task_error,
            last_result_id,
        )

    if wait_for_all:
        done, _ = wait(futures.keys())
    else:
        done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)

    for future in done:
        meta = futures.pop(future)
        last_result_id = meta["result_id"]
        processed += 1
        task_processed += 1

        try:
            future.result()
            success_count += 1
            task_success += 1
        except Exception as err:
            error_count += 1
            task_error += 1
            print(
                f"[ERROR] task_id={meta['task_id']} result_id={meta['result_id']} error={err}"
            )

        if processed % PRINT_EVERY == 0:
            elapsed = time.time() - start_time
            progress_bar = format_progress_bar(processed, total_results)
            print(
                f"[SYNC] {processed}/{total_results} {progress_bar} "
                f"success={success_count} error={error_count} "
                f"last_result_id={last_result_id} elapsed={elapsed:.1f}s"
            )

    return (
        processed,
        success_count,
        error_count,
        task_processed,
        task_success,
        task_error,
        last_result_id,
    )


if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    processed = 0
    success_count = 0
    error_count = 0
    last_result_id = START_RESULT_ID
    start_time = time.time()

    try:
        cached_task_ids = load_cached_task_ids()
        tasks = iter_task_ids(conn, TARGET_TASK_ID, START_RESULT_ID)

        runnable_tasks = []
        skipped_by_cache = 0
        skipped_empty = 0

        for task in tasks:
            if task["id"] in cached_task_ids:
                skipped_by_cache += 1
                print(f"[CACHE_SKIP] task_id={task['id']} name={task['name']}")
                continue
            if (task["result_count"] or 0) <= 0:
                skipped_empty += 1
                continue
            runnable_tasks.append(task)

        total_results = sum(task["result_count"] or 0 for task in runnable_tasks)
        print(
            f"[START] tasks={len(tasks)} run={len(runnable_tasks)} cached_skip={skipped_by_cache} "
            f"empty_skip={skipped_empty} total_results={total_results} target={TARGET_TASK_ID or 'ALL'} "
            f"workers={MAX_WORKERS} inflight={MAX_IN_FLIGHT}"
        )

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for task in runnable_tasks:
                task_processed = 0
                task_success = 0
                task_error = 0
                task_start_time = time.time()
                futures = {}

                print(
                    f"[TASK] start task_id={task['id']} type={task['task_type']} "
                    f"count={task['result_count']} name={task['name']}"
                )

                for row in iter_task_rows(
                    conn=conn,
                    task_id=task["id"],
                    start_result_id=START_RESULT_ID,
                    batch_size=BATCH_SIZE,
                ):
                    if row["task_type"] == "google_sheet":
                        payload = build_c3_payload(row)
                    elif row["task_type"] == "google_sheet_C5":
                        payload = build_c5_payload(row)
                    else:
                        continue

                    if PRINT_PAYLOAD:
                        print(json.dumps(payload, ensure_ascii=False))

                    if DRY_RUN:
                        future = executor.submit(lambda: "dry-run")
                    else:
                        future = executor.submit(send_request, payload)

                    futures[future] = {
                        "task_id": row["task_id"],
                        "result_id": row["id"],
                    }

                    if len(futures) >= MAX_IN_FLIGHT:
                        (
                            processed,
                            success_count,
                            error_count,
                            task_processed,
                            task_success,
                            task_error,
                            last_result_id,
                        ) = handle_completed_futures(
                            futures=futures,
                            processed=processed,
                            success_count=success_count,
                            error_count=error_count,
                            task_processed=task_processed,
                            task_success=task_success,
                            task_error=task_error,
                            total_results=total_results,
                            last_result_id=last_result_id,
                            start_time=start_time,
                            wait_for_all=False,
                        )

                (
                    processed,
                    success_count,
                    error_count,
                    task_processed,
                    task_success,
                    task_error,
                    last_result_id,
                ) = handle_completed_futures(
                    futures=futures,
                    processed=processed,
                    success_count=success_count,
                    error_count=error_count,
                    task_processed=task_processed,
                    task_success=task_success,
                    task_error=task_error,
                    total_results=total_results,
                    last_result_id=last_result_id,
                    start_time=start_time,
                    wait_for_all=True,
                )

                task_elapsed = time.time() - task_start_time
                progress_bar = format_progress_bar(processed, total_results)
                print(
                    f"[TASK_DONE] {processed}/{total_results} {progress_bar} "
                    f"task_id={task['id']} processed={task_processed} success={task_success} "
                    f"error={task_error} elapsed={task_elapsed:.1f}s"
                )

                if not DRY_RUN and task_processed > 0 and task_error == 0:
                    append_cached_task_id(task["id"])
                    cached_task_ids.add(task["id"])
                    print(f"[CACHE_WRITE] task_id={task['id']}")

        elapsed = time.time() - start_time
        progress_bar = format_progress_bar(processed, total_results)
        print(
            f"[DONE] {processed}/{total_results} {progress_bar} "
            f"success={success_count} error={error_count} "
            f"last_result_id={last_result_id} elapsed={elapsed:.1f}s"
        )
    finally:
        conn.close()
