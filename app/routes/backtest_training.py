"""Backtest training page routes."""

import json
import math
import re

from flask import Blueprint, current_app, jsonify, render_template, request
from sqlalchemy.orm import load_only

from app.models import Task, TaskResult
from app.services.backtest_excel_service import BacktestExcelService
from app.utils.dfcf_api import DFCJStockApi

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")

C3_PARAMETER_FIELDS = [
    ("commission", "Commission"),
    ("xm", "X Multiplier"),
    ("dbbh1", "单边保护1"),
    ("dbbh2", "单边保护2"),
    ("zlxc", "中立限仓"),
    ("zsgz", "指数跟踪"),
    ("ywf1", "一窝蜂 smoothing"),
    ("ywf2", "一窝蜂 bordering"),
]


def _sanitize_json_value(value):
    """Convert NaN/Infinity values into JSON-safe nulls."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _strip_html_tags(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _infer_backtest_model_version(config):
    if not isinstance(config, dict):
        return "c3"

    sheet = config.get("sheet") or {}
    title = str(sheet.get("title") or config.get("title") or "").upper()
    if "C5" in title or "C4" in title:
        return "c5"

    parameters = config.get("parameters") or []
    first_row = parameters[0] if parameters and isinstance(parameters[0], list) else []
    if len(first_row) == 2:
        return "c5"
    return "c3"


def _parse_percent_like_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None

    raw = str(value).strip()
    if not raw or raw == "-":
        return None

    normalized = raw.replace(",", "").replace("$", "")
    try:
        if normalized.endswith("%"):
            return float(normalized[:-1]) / 100
        return float(normalized)
    except (TypeError, ValueError):
        return raw


def _extract_task_result_payload(task_result):
    try:
        result_payload = json.loads(task_result.result) if task_result.result else {}
    except (TypeError, json.JSONDecodeError):
        result_payload = {}

    value = list(result_payload.values())[0] if isinstance(result_payload, dict) and result_payload else {}
    if not isinstance(value, dict):
        return {}, {}

    calculate_metrics = value.get("calculate_metrics")
    sheet_result = {
        key: item
        for key, item in value.items()
        if key != "calculate_metrics"
    }
    return (
        calculate_metrics if isinstance(calculate_metrics, dict) else {},
        sheet_result,
    )


def _extract_year_drawdown_map(section):
    if not isinstance(section, dict):
        return {}
    return {
        str(item.get("year")): item
        for item in section.get("year_maximum_drawdown", [])
        if isinstance(item, dict) and item.get("year") not in (None, "", "all")
    }


def _extract_year_sharpe_map(section):
    if not isinstance(section, dict):
        return {}

    year_map = {}
    for key, value in section.items():
        if not isinstance(value, dict):
            continue
        match = re.match(r"^year_\d+_(\d{4})$", str(key))
        if match:
            year_map[match.group(1)] = value
    return year_map


def _extract_display_year(source_window):
    raw = str(source_window or "").strip()
    if not raw:
        return ""

    if re.fullmatch(r"\d{4}-\d{4}", raw):
        end_year, start_year = raw.split("-", 1)
        return start_year or end_year

    return raw


def _build_c3_summary_rows(task_id):
    task_results = (
        TaskResult.query
        .options(
            load_only(
                TaskResult.id,
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.parameters,
                TaskResult.result,
                TaskResult.success,
                TaskResult.timestamp,
            )
        )
        .filter_by(task_id=task_id, success=True)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .all()
    )

    rows = []

    for task_result in task_results:
        try:
            parameters = json.loads(task_result.parameters) if task_result.parameters else {}
        except (TypeError, json.JSONDecodeError):
            parameters = {}

        if not isinstance(parameters, dict):
            continue

        parameter_values = parameters.get("parameter")
        if not isinstance(parameter_values, list) or not parameter_values:
            continue

        parameter_map = {}
        for index, (field_key, _field_label) in enumerate(C3_PARAMETER_FIELDS):
            parameter_map[field_key] = parameter_values[index] if index < len(parameter_values) else None

        calculate_metrics, sheet_result = _extract_task_result_payload(task_result)
        index_sharpe_all = (
            (calculate_metrics.get("index_sharpe_ratios") or {}).get("all")
            if isinstance(calculate_metrics.get("index_sharpe_ratios"), dict)
            else {}
        ) or {}
        start_sharpe_all = (
            (calculate_metrics.get("start_sharpe_ratios") or {}).get("all")
            if isinstance(calculate_metrics.get("start_sharpe_ratios"), dict)
            else {}
        ) or {}
        excess_returns = calculate_metrics.get("excess_returns") or []
        all_excess = next(
            (
                item for item in excess_returns
                if isinstance(item, dict) and str(item.get("year")) == "all"
            ),
            {}
        )

        source_window = str(parameters.get("year") or parameters.get("Kline_key") or "")
        year_label = _extract_display_year(source_window)
        parameter_signature = json.dumps(parameter_values, ensure_ascii=False)

        strategy_return = _parse_percent_like_value(sheet_result.get("I15"))
        index_return = _parse_percent_like_value(sheet_result.get("I18"))
        beats_index = None
        if isinstance(strategy_return, (int, float)) and isinstance(index_return, (int, float)):
            beats_index = strategy_return - index_return
        else:
            beats_index = _parse_percent_like_value(all_excess.get("annualized_return_diff"))

        strategy_max_drawdown = _parse_percent_like_value(sheet_result.get("I17"))
        index_max_drawdown = _parse_percent_like_value(sheet_result.get("I20"))
        drawdown_beats = None
        if isinstance(strategy_max_drawdown, (int, float)) and isinstance(index_max_drawdown, (int, float)):
            drawdown_beats = strategy_max_drawdown - index_max_drawdown

        rows.append({
            **parameter_map,
            "year": year_label,
            "strategy_return": strategy_return,
            "index_return": index_return,
            "beats_index": beats_index,
            "strategy_max_drawdown": strategy_max_drawdown,
            "index_max_drawdown": index_max_drawdown,
            "drawdown_beats": drawdown_beats,
            "fee_total": _parse_percent_like_value(sheet_result.get("I22")),
            "fee_annualized": _parse_percent_like_value(sheet_result.get("I22")),
            "year_rate": _parse_percent_like_value(sheet_result.get("I23")),
            "index_monthly_sharpe": _parse_percent_like_value(index_sharpe_all.get("sharpe_ratio")),
            "strategy_monthly_sharpe": _parse_percent_like_value(start_sharpe_all.get("sharpe_ratio")),
            "date_range": all_excess.get("start_end_date"),
            "source_window": source_window,
            "task_result_id": task_result.id,
            "step_index": task_result.step_index,
            "timestamp": task_result.timestamp.isoformat() if task_result.timestamp else None,
            "parameter_signature": parameter_signature,
        })

    rows.sort(
        key=lambda item: (
            item.get("parameter_signature") or "",
            -(int(item.get("year")) if str(item.get("year", "")).isdigit() else -9999),
            item.get("step_index") or 0,
        )
    )

    parameter_group_count = len({row["parameter_signature"] for row in rows})
    for row in rows:
        row.pop("parameter_signature", None)

    return rows, parameter_group_count


@bp.route("/create")
def create_page():
    return render_template("backtest_training/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_training/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_training/detail.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_result = TaskResult.query.get(result_id)
    task_id = task_result.task_id if task_result else ""
    return render_template("backtest_training/result.html", result_id=result_id, task_id=task_id)


@bp.route("/api/import-excel", methods=["POST"])
def import_excel():
    excel_file = request.files.get("file")
    if not excel_file or not excel_file.filename:
        return jsonify({
            "status": "error",
            "message": "请先上传 Excel 文件",
        }), 400

    try:
        data = BacktestExcelService().import_uploaded_excel(excel_file)
        return jsonify({
            "status": "success",
            **_sanitize_json_value(data),
        })
    except ValueError as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 400
    except Exception as exc:
        current_app.logger.exception("Failed to import backtest Excel")
        return jsonify({
            "status": "error",
            "message": f"Excel 解析失败：{str(exc)}",
        }), 500


@bp.route("/api/search-stocks", methods=["GET"])
def search_stocks():
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=8, type=int) or 8
    page_size = max(1, min(page_size, 20))

    if len(keyword) < 1:
        return jsonify({
            "status": "success",
            "keyword": keyword,
            "results": [],
        })

    raw_results = DFCJStockApi().get_search_list_by_stock_code(keyword, page_size=page_size)
    if isinstance(raw_results, dict) and raw_results.get("error"):
        return jsonify({
            "status": "error",
            "message": raw_results.get("error") or "股票搜索失败",
        }), 502

    normalized_results = []
    for item in raw_results or []:
        if item.get("status") not in (10, "10", None):
            continue
        code = _strip_html_tags(item.get("code"))
        short_name = _strip_html_tags(item.get("shortName"))
        security_type_name = _strip_html_tags(item.get("securityTypeName"))
        market = item.get("market")
        if not code:
            continue
        normalized_results.append({
            "code": code,
            "name": short_name,
            "security_type_name": security_type_name,
            "market": market,
            "is_exact_match": bool(item.get("isExactMatch")),
            "label": " · ".join(part for part in [code, short_name, security_type_name] if part),
        })

    return jsonify({
        "status": "success",
        "keyword": keyword,
        "results": normalized_results,
    })


@bp.route("/api/task-results/<task_id>", methods=["GET"])
def get_task_results_by_task_id(task_id):
    """Return paginated task result summaries for the detail page."""
    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=10, type=int) or 10
    page = max(page, 1)
    per_page = max(min(per_page, 100), 1)

    pagination = (
        TaskResult.query
        .options(
            load_only(
                TaskResult.id,
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.parameters,
                TaskResult.success,
                TaskResult.error_message,
                TaskResult.timestamp,
            )
        )
        .filter_by(task_id=task_id)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    results = [
        {
            "id": task_result.id,
            "task_id": task_result.task_id,
            "step_index": task_result.step_index,
            "parameters": json.loads(task_result.parameters) if task_result.parameters else {},
            "success": task_result.success,
            "error_message": task_result.error_message,
            "timestamp": task_result.timestamp.isoformat() if task_result.timestamp else None,
        }
        for task_result in pagination.items
    ]

    return jsonify({
        "status": "success",
        "task_id": task_id,
        "results": results,
        "pagination": {
            "page": pagination.page,
            "per_page": per_page,
            "pages": pagination.pages,
            "total": pagination.total,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
        },
    })


@bp.route("/api/task-result/<int:task_result_id>", methods=["GET"])
def get_task_result_detail(task_result_id):
    """Return the full task result payload for the result page."""
    task_result = (
        TaskResult.query
        .options(
            load_only(
                TaskResult.result
            )
        )
        .filter(TaskResult.id == task_result_id)
        .first()
    )
    if not task_result:
        return jsonify({
            "status": "error",
            "message": "任务结果不存在",
        }), 404

    result_payload = task_result.to_dict().get("result") or {}
    val = list(result_payload.values())[0] if result_payload else {}
    calculate_metrics = val.get("calculate_metrics") if isinstance(val, dict) else {}
    sheet_result = {
        key: item
        for key, item in val.items()
        if key != "calculate_metrics"
    } if isinstance(val, dict) else {}

    return jsonify({
        "status": "success",
        "result": _sanitize_json_value({
            **(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "sheet_result": sheet_result,
        }),
    })


@bp.route("/api/task-summary/<task_id>", methods=["GET"])
def get_task_summary(task_id):
    task = (
        Task.query
        .options(load_only(Task.id, Task.name, Task.config, Task.task_type))
        .filter(Task.id == task_id)
        .first()
    )
    if not task:
        return jsonify({
            "status": "error",
            "message": "任务不存在",
        }), 404

    task_config = task.to_dict().get("config") or {}
    model_version = _infer_backtest_model_version(task_config)
    if model_version != "c3":
        return jsonify({
            "status": "error",
            "message": "当前汇总页仅支持 C3 回测任务",
        }), 400

    rows, parameter_group_count = _build_c3_summary_rows(task_id)

    return jsonify({
        "status": "success",
        "task": {
            "id": task.id,
            "name": task.name,
            "model_version": model_version,
        },
        "parameter_fields": [
            {"key": field_key, "label": field_label}
            for field_key, field_label in C3_PARAMETER_FIELDS
        ],
        "summary": {
            "row_count": len(rows),
            "parameter_group_count": parameter_group_count,
        },
        "rows": _sanitize_json_value(rows),
    })
