"""Backtest training page routes."""

import json
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, g
from sqlalchemy.orm import load_only
from app.extensions import db
from app.models import Task, TaskResult
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_training_api_service import _sanitize_json_value, _strip_html_tags, \
    _load_backtest_task_or_response, _load_backtest_task_result_or_response, _build_backtest_result_export_data, \
    _build_backtest_result_export_rows, C3_PARAMETER_FIELDS, _build_c3_summary_rows, _infer_backtest_model_version, \
    _build_global_preview_payload, _build_global_preview_workbook, _validate_batch_global_preview_task_ids, \
    _build_zip_member_name
from app.services.stock_metadata_service import bulk_upsert_stock_metadata
from app.services.xpl_service import xpl_analyzer
from app.utils.dfcf_api import DFCJStockApi
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


@bp.route("/api/search-stocks", methods=["GET"])
@login_required
@permission_required('backtest:view')
def search_stocks():
    """按关键词搜索可用于单品回测的股票。"""
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=10, type=int) or 10
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
            "source": item.get("source"),
            "code": code,
            "name": short_name,
            "security_type_name": security_type_name,
            "market": market,
            "is_exact_match": bool(item.get("isExactMatch")),
            "label": " · ".join(part for part in [code, short_name, security_type_name] if part),
            "status": item.get("status"),
            "inner_code": item.get("innerCode"),
            "pinyin": item.get("pinyin"),
            "security_type": item.get("securityType"),
            "small_type": item.get("smallType"),
            "flag": item.get("flag"),
            "ext_small_type": item.get("extSmallType"),
            "quote_id": item.get("quoteId"),
            "market_type": item.get("marketType"),
            "unified_code": item.get("unifiedCode"),
            "jys": item.get("jys"),
            "classify": item.get("classify"),
        })

    bulk_upsert_stock_metadata([
        {
            "stock_code": item.get("code"),
            "stock_name": item.get("name"),
            "market_type": item.get("market_type") or item.get("market"),
            "exchange_market": item.get("market"),
            "security_type_name": item.get("security_type_name"),
            "source": item.get("source"),
            "raw": item,
        }
        for item in normalized_results
    ])
    db.session.commit()

    return jsonify({
        "status": "success",
        "keyword": keyword,
        "results": normalized_results,
    })


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
