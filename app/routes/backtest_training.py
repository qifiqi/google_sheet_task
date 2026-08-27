"""Backtest training page routes."""

import json
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, g
from sqlalchemy.orm import load_only
from app.extensions import db
from app.models import Task, TaskResult
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_training_api_service import _sanitize_json_value, \
    _load_backtest_task_or_response, _load_backtest_task_result_or_response, _build_backtest_result_export_data, \
    _build_backtest_result_export_rows, C3_PARAMETER_FIELDS, _build_c3_summary_rows, _infer_backtest_model_version, \
    _build_global_preview_payload, _build_global_preview_workbook, _validate_batch_global_preview_task_ids, \
    _build_zip_member_name
from app.services.xpl_service import xpl_analyzer
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")
legacy_bp = Blueprint("backtest_training_legacy", __name__, url_prefix="/backtest")


@bp.route("/create")
def create_page():
    return render_template("backtest_training/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_training/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_training/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    return render_template("backtest_training/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_result = TaskResult.query.get(result_id)
    task_id = ""
    if task_result and task_result.task and normalize_task_type(task_result.task.task_type) == "backtest_training":
        task_id = task_result.task_id
    return render_template("backtest_training/result.html", result_id=result_id, task_id=task_id)


@bp.route("/result/<int:result_id>/export-preview")
def result_export_preview_page(result_id):
    return render_template(
        "backtest_training/result_export_preview.html",
        result_id=result_id,
    )


legacy_bp.add_url_rule("/create", view_func=create_page)
legacy_bp.add_url_rule("/list", view_func=list_page)
legacy_bp.add_url_rule("/detail/<task_id>", view_func=detail_page)
legacy_bp.add_url_rule("/global-preview/<task_id>", view_func=global_preview_page)
legacy_bp.add_url_rule("/result/<int:result_id>", view_func=result_page)
legacy_bp.add_url_rule("/result/<int:result_id>/export-preview", view_func=result_export_preview_page)


@bp.route("/api/import-excel", methods=["POST"])
@login_required
@permission_required('backtest:create')
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


@bp.route("/api/task-results/<task_id>", methods=["GET"])
@login_required
@permission_required('backtest:view')
def get_task_results_by_task_id(task_id):
    """Return paginated task result summaries for the detail page."""
    _, error_response = _load_backtest_task_or_response(task_id, action="view")
    if error_response:
        return error_response

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
@login_required
@permission_required('backtest:view')
def get_task_result_detail(task_result_id):
    """Return the full task result payload for the result page."""
    task_result, task, error_response = _load_backtest_task_result_or_response(task_result_id)
    if error_response:
        return error_response

    export_data = _build_backtest_result_export_data(task_result, task)

    return jsonify({
        "status": "success",
        "result": _sanitize_json_value(export_data["analyze_result"]),
    })


@bp.route("/api/task-result/<int:task_result_id>/export-preview", methods=["GET"])
@login_required
@permission_required('backtest:view')
def get_task_result_export_preview(task_result_id):
    task_result, task, error_response = _load_backtest_task_result_or_response(task_result_id)
    if error_response:
        return error_response

    try:
        export_data = _build_backtest_result_export_data(task_result, task)
        rows = _build_backtest_result_export_rows(export_data)
    except Exception:
        current_app.logger.exception("Failed to build backtest result export preview")
        return jsonify({
            "status": "error",
            "message": "预览数据生成失败",
        }), 500

    return jsonify({
        "status": "success",
        "filename": export_data["filename"],
        "rows": rows,
    })


def download_task_result_export_preview(task_result_id):
    task_result, task, error_response = _load_backtest_task_result_or_response(task_result_id)
    if error_response:
        return error_response

    try:
        export_data = _build_backtest_result_export_data(task_result, task)
        export_file, mimetype = xpl_analyzer.export_file(export_data)
    except Exception:
        current_app.logger.exception("Failed to export backtest result preview")
        return jsonify({
            "status": "error",
            "message": "导出数据生成失败",
        }), 500

    return send_file(
        export_file,
        mimetype=mimetype,
        as_attachment=True,
        download_name=export_data["filename"],
    )


@bp.route("/api/task-summary/<task_id>", methods=["GET"])
@login_required
@permission_required('backtest:view')
def get_task_summary(task_id):
    task, error_response = _load_backtest_task_or_response(task_id, action="view")
    if error_response:
        return error_response

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


@bp.route("/api/global-preview/<task_id>", methods=["GET"])
@login_required
@permission_required('backtest:view')
def get_global_preview(task_id):
    _, error_response = _load_backtest_task_or_response(task_id, action="view")
    if error_response:
        return error_response

    payload = _build_global_preview_payload(task_id)
    if payload is None:
        return jsonify({
            "status": "error",
            "message": "任务不存在",
        }), 404

    return jsonify({
        "status": "success",
        **_sanitize_json_value(payload),
    })


def export_global_preview(task_id):
    _, error_response = _load_backtest_task_or_response(task_id, action="view")
    if error_response:
        return error_response

    payload = _build_global_preview_payload(task_id)
    if payload is None:
        return jsonify({
            "status": "error",
            "message": "任务不存在",
        }), 404

    workbook = _build_global_preview_workbook(payload)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    task_name = (payload.get("task") or {}).get("name") or task_id
    safe_name = "".join(char if char not in '\\/:*?\"<>|' else "_" for char in str(task_name)).strip() or task_id
    filename = f"{safe_name}_global_preview.xlsx"

    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


def batch_export_global_preview():
    data = request.get_json(silent=True) or {}
    task_ids, error_response = _validate_batch_global_preview_task_ids(data.get("task_ids"))
    if error_response:
        return error_response

    zip_buffer = BytesIO()
    used_names: set[str] = set()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as archive:
        for task_id in task_ids:
            task, task_error_response = _load_backtest_task_or_response(task_id, action="view")
            if task_error_response:
                return task_error_response
            if task.status != "completed":
                return jsonify({
                    "status": "error",
                    "message": f"任务 {task.name or task_id} 尚未完成，不能导出",
                    "task_id": task_id,
                    "task_status": task.status,
                }), 400

            payload = _build_global_preview_payload(task_id)
            if payload is None:
                return jsonify({
                    "status": "error",
                    "message": "任务不存在",
                    "task_id": task_id,
                }), 404

            workbook = _build_global_preview_workbook(payload)
            workbook_buffer = BytesIO()
            workbook.save(workbook_buffer)
            archive.writestr(
                _build_zip_member_name(task.name, task_id, used_names),
                workbook_buffer.getvalue(),
            )

    zip_buffer.seek(0)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"backtest_global_preview_batch_{stamp}.zip",
    )
