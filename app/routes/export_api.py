"""统一文件导出接口。"""

from __future__ import annotations

import json
from urllib.parse import quote

from dataclasses import replace
from flask import Blueprint, Response, g, jsonify, request, send_file, stream_with_context

from app.extensions import db
from app.models import Task, TaskResult
from app.services.export_service import export_service
from app.services.export_file_service import sanitize_export_filename
from app.utils.auth import login_required
from app.utils.logger import get_logger


logger = get_logger(__name__)
export_api_bp = Blueprint("export_api", __name__)

def _load_task(task_id: str):
    task = db.session.get(Task, task_id)
    if not task:
        return None, (jsonify({"status": "error", "message": "任务不存在"}), 404)
    return task, None


def _completed_task_error(task: Task):
    if str(task.status or "").lower() == "completed":
        return None
    return jsonify({
        "status": "error",
        "message": f"任务 {task.name or task.id} 尚未完成，不能导出",
        "task_id": task.id,
        "task_status": task.status,
    }), 400


def _file_response(generated):
    response = send_file(
        generated.buffer,
        mimetype=generated.mimetype,
        as_attachment=True,
        download_name=generated.filename,
    )
    if generated.file_size is not None:
        response.headers["Content-Length"] = str(generated.file_size)
    return response


def _stream_response(generated):
    """构建流式文件响应，并统一处理 UTF-8 文件名。"""
    encoded_name = quote(str(generated.filename), safe="")
    return Response(
        stream_with_context(generated.generate()),
        mimetype=generated.mimetype,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{generated.filename}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
        },
    )


def _parse_ratios_query():
    raw_ratios = request.args.get("ratios")
    if not raw_ratios:
        return None, None
    try:
        ratios = json.loads(raw_ratios)
    except (TypeError, json.JSONDecodeError):
        return None, (jsonify({"status": "error", "message": "ratios 参数不是有效 JSON"}), 400)
    if not isinstance(ratios, list):
        return None, (jsonify({"status": "error", "message": "ratios 参数必须是数组"}), 400)
    return ratios, None


@export_api_bp.route("/tasks/<task_id>", methods=["GET"])
@login_required
def export_task_results(task_id):
    task, error = _load_task(task_id)
    if error:
        return error
    completed_error = _completed_task_error(task)
    if completed_error:
        return completed_error
    try:
        return _file_response(export_service.export_task_results(task.id))
    except (ValueError, LookupError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出任务结果失败 task_id=%s", task_id)
        return jsonify({"status": "error", "message": "导出任务结果失败"}), 500


@export_api_bp.route("/tasks/<task_id>/stocks", methods=["GET"])
@login_required
def export_task_results_by_stock(task_id):
    task, error = _load_task(task_id)
    if error:
        return error
    completed_error = _completed_task_error(task)
    if completed_error:
        return completed_error
    try:
        return _file_response(export_service.export_task_results_by_stock(task.id))
    except (ValueError, LookupError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("按股票导出任务结果失败 task_id=%s", task_id)
        return jsonify({"status": "error", "message": "导出任务结果失败"}), 500


@export_api_bp.route("/tasks/batch", methods=["POST"])
@login_required
def export_task_results_batch():
    try:
        data = request.get_json(silent=True) or {}
        task_ids = data.get("task_ids")
        if not isinstance(task_ids, list):
            return jsonify({"status": "error", "message": "task_ids 必须是数组"}), 400
        return _file_response(export_service.export_task_results_batch(task_ids))
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("批量导出任务结果失败")
        return jsonify({"status": "error", "message": "批量导出任务结果失败"}), 500


@export_api_bp.route("/global-previews/<task_id>", methods=["GET"])
@login_required
def export_global_preview(task_id):
    task, error = _load_task(task_id)
    if error:
        return error
    completed_error = _completed_task_error(task)
    if completed_error:
        return completed_error
    ratios, error = _parse_ratios_query()
    if error:
        return error
    try:
        generated = export_service.export_global_preview(task.id, ratios_override=ratios)
        export_name = request.args.get("export_name")
        if export_name:
            generated = replace(
                generated,
                filename=f"{sanitize_export_filename(export_name)}.xlsx",
            )
        return _file_response(generated)
    except (ValueError, LookupError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出全局预览失败 task_id=%s", task_id)
        return jsonify({"status": "error", "message": "导出全局预览失败"}), 500


@export_api_bp.route("/global-previews/<task_id>/stocks", methods=["GET"])
@login_required
def export_global_preview_by_stock(task_id):
    task, error = _load_task(task_id)
    if error:
        return error
    completed_error = _completed_task_error(task)
    if completed_error:
        return completed_error
    ratios, error = _parse_ratios_query()
    if error:
        return error
    try:
        generated = export_service.export_global_preview_by_stock(task.id, ratios_override=ratios)
        return _stream_response(generated)
    except (ValueError, LookupError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("按股票导出全局预览失败 task_id=%s", task_id)
        return jsonify({"status": "error", "message": "导出全局预览失败"}), 500


@export_api_bp.route("/global-previews/batch", methods=["POST"])
@login_required
def export_global_preview_batch():
    try:
        data = request.get_json(silent=True) or {}
        task_ids = data.get("task_ids")
        if not isinstance(task_ids, list):
            return jsonify({"status": "error", "message": "task_ids 必须是数组"}), 400
        normalized_ids = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
        return _file_response(export_service.export_global_preview_batch(normalized_ids))
    except LookupError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("批量导出全局预览失败")
        return jsonify({"status": "error", "message": "批量导出全局预览失败"}), 500


@export_api_bp.route("/backtest-results/<int:result_id>", methods=["GET"])
@login_required
def export_backtest_result(result_id):
    task_result = TaskResult.query.filter(TaskResult.id == result_id).first()
    if not task_result:
        return jsonify({"status": "error", "message": "任务结果不存在"}), 404
    task, error = _load_task(task_result.task_id)
    if error:
        return error
    try:
        return _file_response(export_service.export_backtest_result(result_id))
    except (ValueError, LookupError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出回测结果失败 result_id=%s", result_id)
        return jsonify({"status": "error", "message": "导出回测结果失败"}), 500


@export_api_bp.route("/xpl", methods=["POST"])
@login_required
def export_xpl():
    try:
        return _file_response(export_service.export_xpl(request.get_json(silent=True) or {}))
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出 XPL 文件失败")
        return jsonify({"status": "error", "message": "导出 XPL 文件失败"}), 500


@export_api_bp.route("/backtest-reports/word", methods=["POST"])
@login_required
def export_backtest_word_report():
    """接收单产品或多产品回测收益序列并导出 DOCX 报告。"""
    try:
        generated = export_service.export_backtest_word(request.get_json(silent=True) or {})
        generated = replace(
            generated,
            filename=sanitize_export_filename(generated.filename, "策略回测绩效分析报告.docx"),
        )
        return _file_response(generated)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出策略回测 Word 报告失败")
        return jsonify({"status": "error", "message": "导出策略回测 Word 报告失败"}), 500


@export_api_bp.route("/model-summary", methods=["GET"])
@login_required
def export_model_summary():
    try:
        generated = export_service.export_model_summary(
            getattr(g, "current_user", None),
            request.args.to_dict(),
            ignore_permissions=True,
        )
        return _file_response(generated)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception:
        logger.exception("导出模型汇总失败")
        return jsonify({"status": "error", "message": "导出模型汇总失败"}), 500
