"""一次性迁移历史任务数据到统一运行时契约。

默认 dry-run；加 --apply 才写库。幂等，可按 id 分批续跑。

覆盖：
1. C11 -> C1.1 标识（task_type/table_type/summary_index/permission/nav/system_config）。
2. 任务配置与模板：c7_model_version -> model_version，补全 sheets[].model_version。
3. 历史结果：flat_result/analyze_result/calculate_metrics ->
   metrics_payload={schema_version, metrics, canonical_metrics}；参数
   Kline_key -> kline_key、删除 year、c7_model_version -> model_version。

用法：
  python scripts/migrate_runtime_contract.py --env-file .env.testing --dry-run
  python scripts/migrate_runtime_contract.py --env-file .env.testing --apply \
      --skip-results
  python scripts/migrate_runtime_contract.py --env-file .env.testing --apply \
      --limit-results 5000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.model_version import infer_model_version, normalize_model_version


LEGACY_METRIC_ALIASES = {
    "index_sotino_ratio": "index_sortino_ratio",
    "start_sotino_ratio": "start_sortino_ratio",
    "index_weekly_sotino_ratio": "index_weekly_sortino_ratio",
    "start_weekly_sotino_ratio": "start_weekly_sortino_ratio",
    "sotino_ratio": "sortino_ratio",
    "excess_sharp": "excess_sharpe",
    "excess_of_promissory_note": "excess_sortino",
    "cumulative_excess": "excess_cumulative_return",
    "excess_net": "excess_nav",
}

LEGACY_RESULT_KEYS = (
    "flat_result",
    "analyze_result",
    "calculate_metrics",
    "weighted_calculate_metrics",
)

OLD_TASK_TYPES = {"google_sheet_c11": "google_sheet_C1_1"}


def load_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def rename_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            LEGACY_METRIC_ALIASES.get(str(key), key): rename_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [rename_keys(item) for item in value]
    return value


def _all_entry(items: Any) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get("year")) == "all":
            return item
    return {}


def _num(value: Any) -> Any:
    if value is None:
        return 0
    if isinstance(value, bool):
        return value
    try:
        if isinstance(value, str):
            text_value = value.strip().replace("%", "").replace(",", "")
            if text_value == "":
                return 0
            return float(text_value)
        return value
    except (TypeError, ValueError):
        return value


def expand_flat_metrics(flat: dict[str, Any]) -> dict[str, Any]:
    """把旧扁平投影还原为可被 flatten_v1_metrics 读取的 metrics 树。"""
    metrics = dict(flat)
    for prefix in ("start", "index"):
        sharpe = metrics.pop(f"{prefix}_sharpe_ratio", None)
        monthly = metrics.pop(f"{prefix}_monthly_std_dev", None)
        annual = metrics.pop(f"{prefix}_annual_std_dev", None)
        values = {
            key: value
            for key, value in (
                ("sharpe_ratio", sharpe),
                ("monthly_std_dev", monthly),
                ("annual_std_dev", annual),
            )
            if value is not None
        }
        if values:
            metrics.setdefault(f"{prefix}_sharpe_ratios", {})["all"] = values
    if "monthly_excess_return_percentage_last_return" in metrics:
        value = metrics.pop("monthly_excess_return_percentage_last_return")
        metrics["monthly_excess_return_percentage"] = [
            {"year": "all", "excess_return": value}
        ]
    annualized_diff = metrics.pop("annualized_return_diff", None)
    if annualized_diff is not None and not metrics.get("excess_returns"):
        metrics["excess_returns"] = [
            {"year": "all", "annualized_return_diff": annualized_diff}
        ]
    for key, field in (("index_kama_ratio", "kama_ratio"), ("start_kama_ratio", "kama_ratio")):
        if key in metrics and not isinstance(metrics[key], list):
            metrics[key] = [{"year": "all", field: metrics[key]}]
    for key, field in (("index_sortino_ratio", "sortino_ratio"), ("start_sortino_ratio", "sortino_ratio")):
        if key in metrics and not isinstance(metrics[key], list):
            metrics[key] = [{"year": "all", field: metrics[key]}]
    return rename_keys(metrics)


def build_canonical_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    index_sharpe = (metrics.get("index_sharpe_ratios") or {}).get("all") or {}
    start_sharpe = (metrics.get("start_sharpe_ratios") or {}).get("all") or {}
    index_sortino = _all_entry(metrics.get("index_sortino_ratio"))
    start_sortino = _all_entry(metrics.get("start_sortino_ratio"))
    excess_return = metrics.get("excess_cumulative_return")
    excess_nav = metrics.get("excess_nav")
    if excess_nav is None and isinstance(excess_return, (int, float)):
        excess_nav = 1 + excess_return
    excess_all = _all_entry(metrics.get("excess_returns"))
    return {
        "period": {
            "start": "",
            "end": "",
        },
        "benchmark": {
            "cumulative_return": metrics.get("index_cumulative_return"),
            "annualized_return": excess_all.get("index_annualized_return", metrics.get("index_annualized_return")),
            "max_drawdown": (
                (metrics.get("index_maximum_drawdown") or {}).get("total_maximum_drawdown") or {}
            ).get("drawdown"),
            "sharpe_ratio": index_sharpe.get("sharpe_ratio"),
            "sortino_ratio": index_sortino.get("sortino_ratio"),
        },
        "strategy": {
            "cumulative_return": metrics.get("start_cumulative_return"),
            "annualized_return": excess_all.get("start_annualized_return", metrics.get("start_annualized_return")),
            "max_drawdown": (
                (metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown") or {}
            ).get("drawdown"),
            "sharpe_ratio": start_sharpe.get("sharpe_ratio"),
            "sortino_ratio": start_sortino.get("sortino_ratio"),
        },
        "relative": {
            "cumulative_excess_return": excess_return,
            "excess_nav": excess_nav,
            "annualized_return": excess_all.get("annualized_return_diff"),
            "excess_sharpe": metrics.get("excess_sharpe"),
            "excess_sortino": metrics.get("excess_sortino"),
        },
        "distributions": {
            "benchmark_daily": metrics.get("index_days_distribution"),
            "strategy_daily": metrics.get("start_days_distribution"),
            "benchmark_monthly": metrics.get("index_monthly_distribution"),
            "strategy_monthly": metrics.get("start_monthly_distribution"),
            "excess_monthly": metrics.get("excess_distribution"),
        },
    }


def normalize_metrics_payload(payload: Any, weighted: Any = None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    canonical = payload.get("canonical_metrics") if isinstance(payload.get("canonical_metrics"), dict) else {}
    canonical = dict(canonical)
    canonical.pop("all_metrics", None)
    canonical.pop("schema_version", None)
    if not canonical:
        canonical = build_canonical_metrics(metrics)
    result = {
        "schema_version": payload.get("schema_version") or "metrics.v1",
        "metrics": rename_keys(metrics),
        "canonical_metrics": canonical,
    }
    if isinstance(weighted, dict) and weighted:
        result["weighted_metrics"] = rename_keys(weighted)
    elif isinstance(payload.get("weighted_metrics"), dict) and payload["weighted_metrics"]:
        result["weighted_metrics"] = rename_keys(payload["weighted_metrics"])
    return result


def transform_result_node(node: Any, stats: dict[str, int]) -> Any:
    if isinstance(node, list):
        return [transform_result_node(item, stats) for item in node]
    if not isinstance(node, dict):
        return node

    weighted = node.get("weighted_calculate_metrics")
    if "metrics_payload" in node:
        node["metrics_payload"] = normalize_metrics_payload(node.get("metrics_payload"), weighted)
        stats["metrics_payload_normalized"] += 1
    elif any(key in node for key in LEGACY_RESULT_KEYS):
        metrics = node.get("analyze_result") or node.get("calculate_metrics")
        if not isinstance(metrics, dict):
            metrics = expand_flat_metrics(node.get("flat_result") or {})
        else:
            metrics = rename_keys(metrics)
        node["metrics_payload"] = normalize_metrics_payload(
            {"metrics": metrics}, weighted
        )
        stats["metrics_payload_built"] += 1
    for key in LEGACY_RESULT_KEYS:
        if key in node:
            node.pop(key, None)
            stats["legacy_keys_removed"] += 1
    for key, value in list(node.items()):
        if key != "metrics_payload":
            node[key] = transform_result_node(value, stats)
    return node


def transform_parameters(parameters: Any, task_type: str, config: Any, stats: dict[str, int]) -> Any:
    if not isinstance(parameters, dict):
        return parameters
    parameters = dict(parameters)
    if "Kline_key" in parameters:
        parameters["kline_key"] = parameters.pop("Kline_key")
        stats["params_kline_key"] += 1
    if "c7_model_version" in parameters:
        parameters["model_version"] = parameters.pop("c7_model_version")
        stats["params_model_version"] += 1
    if "year" in parameters:
        parameters.pop("year")
        stats["params_year_removed"] += 1
    if not normalize_model_version(parameters.get("model_version")):
        sheet = {}
        if isinstance(config, dict):
            sheets = config.get("sheets")
            if isinstance(sheets, list) and sheets and isinstance(sheets[0], dict):
                sheet = sheets[0]
        version = infer_model_version(task_type, sheet)
        if version:
            parameters["model_version"] = version
            stats["params_model_version_added"] += 1
    return parameters


def normalize_config(config: Any, task_type: str) -> Any:
    if not isinstance(config, dict):
        return config
    config = rename_keys(config)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "c7_model_version" in node:
                node["model_version"] = node.pop("c7_model_version")
            return {key: walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    config = walk(config)
    sheets = config.get("sheets")
    if isinstance(sheets, list):
        for sheet in sheets:
            if isinstance(sheet, dict) and not normalize_model_version(sheet.get("model_version")):
                version = infer_model_version(task_type, sheet)
                if version:
                    sheet["model_version"] = version
    products = config.get("products")
    if isinstance(products, list):
        for product in products:
            if not isinstance(product, dict):
                continue
            sheet = product.get("sheet")
            if isinstance(sheet, dict) and not normalize_model_version(sheet.get("model_version")):
                version = infer_model_version(task_type, sheet)
                if version:
                    sheet["model_version"] = version
    return config


def migrate_rbac(conn, apply: bool) -> dict[str, int]:
    stats = {"permission": 0, "nav": 0, "task_type": 0, "table_type": 0, "summary": 0, "syscfg": 0}
    statements = [
        (
            "permission",
            "UPDATE t_param_permission SET code=:new, name=:name, description=:desc, "
            "route_path=:route WHERE id=:id",
            "SELECT id, code, name, route_path FROM t_param_permission WHERE code LIKE '%c11%'",
            lambda row: {
                "new": row.code.replace("c11", "c1_1"),
                "name": (row.name or "").replace("C11", "C1.1").replace("c11", "C1.1"),
                "desc": (row.route_path or "").replace("c11", "c1_1"),
                "route": (row.route_path or "").replace("c11", "c1_1"),
                "id": row.id,
            },
        ),
        (
            "nav",
            "UPDATE t_param_navigation_menu_items SET key=:new_key, label=:label, path=:path, "
            "permission=:permission WHERE id=:id",
            "SELECT id, key, label, path, permission FROM t_param_navigation_menu_items "
            "WHERE key LIKE '%c11%' OR path LIKE '%c11%' OR permission LIKE '%c11%'",
            lambda row: {
                "new_key": (row.key or "").replace("c11", "c1_1"),
                "label": (row.label or "").replace("C11", "C1.1").replace("c11", "C1.1"),
                "path": (row.path or "").replace("c11", "c1_1"),
                "permission": (row.permission or "").replace("c11", "c1_1"),
                "id": row.id,
            },
        ),
        (
            "task_type",
            "UPDATE t_param_tasks SET task_type=:new WHERE id=:id",
            "SELECT id, task_type FROM t_param_tasks WHERE lower(task_type)='google_sheet_c11'",
            lambda row: {"new": "google_sheet_C1_1", "id": row.id},
        ),
        (
            "table_type",
            "UPDATE t_param_google_sheet SET table_type='c1_1' WHERE table_type='c11'",
            None,
            None,
        ),
        (
            "summary",
            "UPDATE t_param_task_result_summary_index SET task_type='google_sheet_C1_1' "
            "WHERE lower(task_type)='google_sheet_c11'",
            None,
            None,
        ),
        (
            "syscfg",
            "UPDATE t_param_system_configs SET key=REPLACE(key, 'c11', 'c1_1') WHERE key LIKE '%c11%'",
            None,
            None,
        ),
    ]
    for name, update_sql, select_sql, mapper in statements:
        if select_sql is None:
            if apply:
                result = conn.execute(text(update_sql))
                stats[name] = result.rowcount or 0
            else:
                stats[name] = 0
            continue
        rows = list(conn.execute(text(select_sql)))
        stats[name] = len(rows)
        if apply and rows:
            conn.execute(text(update_sql), [mapper(row) for row in rows])
    return stats


def migrate_configs(conn, apply: bool) -> dict[str, int]:
    stats = {"tasks": 0, "templates": 0}
    tasks = list(conn.execute(text("SELECT id, task_type, config FROM t_param_tasks")))
    task_updates = []
    for row in tasks:
        config = load_json(row.config)
        if not isinstance(config, dict):
            continue
        new_config = normalize_config(config, row.task_type)
        if new_config != config:
            task_updates.append({"id": row.id, "config": dump_json(new_config)})
    stats["tasks"] = len(task_updates)
    if apply and task_updates:
        conn.execute(
            text("UPDATE t_param_tasks SET config=:config WHERE id=:id"),
            task_updates,
        )

    templates = list(conn.execute(text("SELECT id, config FROM t_param_task_templates")))
    template_updates = []
    for row in templates:
        config = load_json(row.config)
        if not isinstance(config, dict):
            continue
        task_type = config.get("task_type") or ""
        new_config = normalize_config(config, task_type)
        if new_config != config:
            template_updates.append({"id": row.id, "config": dump_json(new_config)})
    stats["templates"] = len(template_updates)
    if apply and template_updates:
        conn.execute(
            text("UPDATE t_param_task_templates SET config=:config WHERE id=:id"),
            template_updates,
        )
    return stats


def apply_result_updates(conn, updates: list[dict[str, Any]]) -> None:
    """单批写入；死锁/锁冲突时回滚并重试，避免整轮迁移被一个批次拖垮。"""
    if not updates:
        return
    for attempt in range(5):
        try:
            if conn.dialect.name == "postgresql":
                from psycopg2.extras import execute_values

                with conn.connection.cursor() as cursor:
                    execute_values(
                        cursor,
                        "UPDATE t_param_task_results AS t SET parameters=v.parameters, result=v.result "
                        "FROM (VALUES %s) AS v(id, parameters, result) WHERE t.id=v.id",
                        [(item["id"], item["parameters"], item["result"]) for item in updates],
                        page_size=len(updates),
                    )
            else:
                conn.execute(
                    text("UPDATE t_param_task_results SET parameters=:parameters, result=:result WHERE id=:id"),
                    updates,
                )
            conn.commit()
            return
        except DBAPIError as exc:
            conn.rollback()
            message = str(exc).lower()
            if attempt >= 4 or ("deadlock" not in message and "lock" not in message and "timeout" not in message):
                raise
            time.sleep(1.5 * (attempt + 1))


def migrate_results(conn, apply: bool, limit: int, batch_size: int, start_id: int) -> dict[str, int]:
    if apply and conn.dialect.name == "postgresql":
        conn.execute(text("SET statement_timeout = '60s'"))
        conn.execute(text("SET lock_timeout = '10s'"))
        conn.commit()
    stats = {
        "scanned": 0,
        "changed": 0,
        "metrics_payload_normalized": 0,
        "metrics_payload_built": 0,
        "legacy_keys_removed": 0,
        "params_kline_key": 0,
        "params_model_version": 0,
        "params_model_version_added": 0,
        "params_year_removed": 0,
    }
    task_meta = {
        row.id: (row.task_type, load_json(row.config))
        for row in conn.execute(text("SELECT id, task_type, config FROM t_param_tasks"))
    }
    candidate_sql = (
        "SELECT id, task_id, parameters, result FROM t_param_task_results "
        "WHERE id > :last_id AND ("
        "result LIKE '%flat_result%' OR result LIKE '%analyze_result%' "
        "OR result LIKE '%calculate_metrics%' OR result LIKE '%metrics_payload%' "
        "OR result LIKE '%all_metrics%' "
        "OR parameters LIKE '%Kline_key%' OR parameters LIKE '%\"year\"%' "
        "OR parameters LIKE '%c7_model_version%'"
        ") ORDER BY id LIMIT :limit"
    )
    last_id = start_id
    remaining = limit if limit > 0 else None
    while True:
        fetch_size = batch_size if remaining is None else min(batch_size, remaining)
        if fetch_size <= 0:
            break
        rows = list(conn.execute(
            text(candidate_sql),
            {"last_id": last_id, "limit": fetch_size},
        ))
        if not rows:
            break
        updates = []
        result_stat_keys = (
            "metrics_payload_normalized",
            "metrics_payload_built",
            "legacy_keys_removed",
        )
        for row in rows:
            stats["scanned"] += 1
            task_type, config = task_meta.get(row.task_id, ("", None))
            parameters = load_json(row.parameters)
            result = load_json(row.result)
            new_parameters = transform_parameters(parameters, task_type, config, stats)
            result_before = {key: stats[key] for key in result_stat_keys}
            new_result = transform_result_node(result, stats) if result is not None else None
            result_changed = any(
                stats[key] > result_before[key] for key in result_stat_keys
            )
            if new_parameters != parameters or result_changed:
                stats["changed"] += 1
                updates.append({
                    "id": row.id,
                    "parameters": dump_json(new_parameters) if new_parameters is not None else row.parameters,
                    "result": dump_json(new_result) if new_result is not None else row.result,
                })
        if apply:
            apply_result_updates(conn, updates)
        last_id = rows[-1].id
        print(
            f"progress id={last_id} scanned={stats['scanned']} changed={stats['changed']} "
            f"built={stats['metrics_payload_built']} normalized={stats['metrics_payload_normalized']}",
            flush=True,
        )
        if remaining is not None:
            remaining -= len(rows)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-rbac", action="store_true")
    parser.add_argument("--skip-configs", action="store_true")
    parser.add_argument("--skip-results", action="store_true")
    parser.add_argument("--limit-results", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--start-id", type=int, default=0)
    args = parser.parse_args()

    url = args.database_url
    if not url and args.env_file:
        url = dotenv_values(args.env_file).get("DATABASE_URL", "")
    if not url:
        url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("缺少数据库连接：传 --database-url 或 --env-file")

    engine = create_engine(url, connect_args={"connect_timeout": 10})
    safe_url = make_url(url)
    print(f"target={safe_url.host}:{safe_url.port}/{safe_url.database} apply={args.apply}")
    with engine.begin() as conn:
        if not args.skip_rbac:
            print("rbac/config migration:", migrate_rbac(conn, args.apply))
        if not args.skip_configs:
            print("task configs:", migrate_configs(conn, args.apply))
    if not args.skip_results:
        with engine.connect() as conn:
            print("results:", migrate_results(
                conn,
                args.apply,
                args.limit_results,
                args.batch_size,
                args.start_id,
            ))


if __name__ == "__main__":
    main()
