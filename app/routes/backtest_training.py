"""Backtest training page routes."""

import json
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, g
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_training_api_service import _sanitize_json_value, \
    _load_backtest_task_or_response, _load_backtest_task_result_or_response, _build_backtest_result_export_data, \
    _build_backtest_result_export_rows, C3_PARAMETER_FIELDS, _build_c3_summary_rows, _infer_backtest_model_version, \
    _extract_task_result_payload, _extract_summary_rows, _infer_backtest_export_model_name, \
    _negative_percent_display, _with_excess_return_preview_row, \
    _build_global_preview_payload, _build_global_preview_workbook, _validate_batch_global_preview_task_ids, \
    _build_zip_member_name
from app.services.xpl_service import xpl_analyzer
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type

bp = Blueprint("backtest_training", __name__, url_prefix="/backtest-training")
legacy_bp = Blueprint("backtest_training_legacy", __name__, url_prefix="/backtest")
_task_repository = TaskRepository()
_task_result_repository = TaskResultRepository()


@bp.route("/create")
def create_page():
    """渲染单品回测任务创建页面。"""
    return render_template("backtest_training/create.html")


@bp.route("/list")
def list_page():
    """渲染单品回测任务列表页面。"""
    return render_template("backtest_training/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    """渲染指定单品回测任务的详情页面。"""
    return render_template("backtest_training/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    """渲染指定任务的全局预览页面。"""
    return render_template("backtest_training/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    """渲染指定单品回测结果的详情页面。"""
    task_result = _task_result_repository.get(result_id)
    task_id = ""
    if task_result:
        task = _task_repository.get(task_result.task_id)
        if task and normalize_task_type(task.task_type) == "backtest_training":
            task_id = task_result.task_id
    return render_template("backtest_training/result.html", result_id=result_id, task_id=task_id)


@bp.route("/result/<int:result_id>/export-preview")
def result_export_preview_page(result_id):
    """渲染任务结果的导出预览页面。"""
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
    """导入 Excel 中的回测股票与参数配置。"""
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
    """返回指定任务的结果列表，并执行任务查看权限校验。"""
    """Return paginated task result summaries for the detail page."""
    _, error_response = _load_backtest_task_or_response(task_id, action="view")
    if error_response:
        return error_response

    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=10, type=int) or 10
    page = max(page, 1)
    per_page = max(min(per_page, 100), 1)

    result_page = _task_result_repository.list_results(
        page_index=page,
        page_size=per_page,
        task_ids=[task_id],
        order_field="step_index",
        order_type="asc",
    )
    results = [
        {
            "id": task_result.id,
            "task_id": task_result.task_id,
            "step_index": task_result.step_index,
            "parameters": task_result.parameters or {},
            "success": task_result.success,
            "error_message": task_result.get("error_message"),
            "timestamp": (
                task_result.timestamp.isoformat()
                if getattr(task_result, "timestamp", None) and hasattr(task_result.timestamp, "isoformat")
                else task_result.get("timestamp")
            ),
        }
        for task_result in result_page["items"]
    ]
    total = result_page["total"]
    pages = (total + per_page - 1) // per_page if total else 0

    return jsonify({
        "status": "success",
        "task_id": task_id,
        "results": results,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "total": total,
            "has_prev": page > 1,
            "has_next": page < pages,
            "prev_num": page - 1 if page > 1 else None,
            "next_num": page + 1 if page < pages else None,
        },
    })


@bp.route("/api/task-result/<int:task_result_id>", methods=["GET"])
@login_required
@permission_required('backtest:view')
def get_task_result_detail(task_result_id):
    """返回一条单品回测结果的完整详情。"""
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
    """构造单条结果的导出预览内容。"""
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


@bp.route("/api/task-result/<int:task_result_id>/export-preview/download", methods=["GET"])
@login_required
@permission_required('backtest:view')
def download_task_result_export_preview(task_result_id):
    """下载单条结果的预览导出文件。"""
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
    """返回指定任务的汇总统计数据。"""
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
    """返回全局预览所需的数据和状态。"""
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


@bp.route("/api/global-preview/<task_id>/export", methods=["GET"])
@login_required
@permission_required('backtest:view')
def export_global_preview(task_id):
    """导出指定任务的全局预览数据。"""
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


@bp.route("/api/global-preview/batch-export", methods=["POST"])
@login_required
@permission_required('backtest:view')
def batch_export_global_preview():
    """批量导出多个单品回测任务的全局预览数据。"""
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
