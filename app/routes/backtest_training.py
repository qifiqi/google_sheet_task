# -*- coding: utf-8 -*-
"""Backtest training page routes."""

import json
import math

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.orm import load_only

from app.models import TaskResult

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")


def _sanitize_json_value(value):
    """Convert NaN/Infinity values into JSON-safe nulls."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


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
