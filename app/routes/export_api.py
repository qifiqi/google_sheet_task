"""统一文件导出接口（数据层：task_repository）。

导出服务的 ValueError/LookupError 语义保持原有 400/404 映射；
其余未预期异常交全局处理器转 500。
"""

from __future__ import annotations

import json
from dataclasses import replace
from urllib.parse import quote

from flask import Blueprint, Response, g, jsonify, request, send_file, stream_with_context

from app.exceptions import BadRequestError, NotFoundError
from app.extensions import limiter
from app.repositories import task_repository, task_result_repository
from app.services.export_service import export_service
from app.services.export_file_service import sanitize_export_filename
from app.utils.auth import login_required
from app.utils.logger import get_logger


logger = get_logger(__name__)
export_api_bp = Blueprint("export_api", __name__)


def _rate_limit(config_key, default):
    """限流阈值经 config_manager 运行时可调（零重启）。"""
    from app.services.config_manager import get_config_manager

    return get_config_manager().get_config(config_key, default)


def _user_key():
    return f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}"


# 06 §3：导出端点统一 rate_limit_export（10/min，user 键）。
_export_limit = limiter.limit(
    lambda: f"{_rate_limit('rate_limit_export', 10) or 10}/minute",
    key_func=_user_key,
)


def _load_task(task_id: str):
    task = task_repository.get(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    return task


def _require_completed_task(task: dict):
    if str(task.get("status") or "").lower() == "completed":
        return
    raise BadRequestError(
        f"任务 {task.get('name') or task.get('id')} 尚未完成，不能导出",
        data={"task_id": task.get("id"), "task_status": task.get("status")},
    )


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
        return None
    try:
        ratios = json.loads(raw_ratios)
    except (TypeError, json.JSONDecodeError):
        raise BadRequestError("ratios 参数不是有效 JSON")
    if not isinstance(ratios, list):
        raise BadRequestError("ratios 参数必须是数组")
    return ratios


@export_api_bp.route("/tasks/<task_id>", methods=["GET"])
@login_required
@_export_limit
def export_task_results(task_id):
    task = _load_task(task_id)
    _require_completed_task(task)
    try:
        return _file_response(export_service.export_task_results(task["id"]))
    except (ValueError, LookupError) as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/tasks/<task_id>/stocks", methods=["GET"])
@login_required
@_export_limit
def export_task_results_by_stock(task_id):
    task = _load_task(task_id)
    _require_completed_task(task)
    try:
        return _file_response(export_service.export_task_results_by_stock(task["id"]))
    except (ValueError, LookupError) as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/tasks/batch", methods=["POST"])
@login_required
@_export_limit
def export_task_results_batch():
    data = request.get_json(silent=True) or {}
    task_ids = data.get("task_ids")
    if not isinstance(task_ids, list):
        raise BadRequestError("task_ids 必须是数组")
    try:
        return _file_response(export_service.export_task_results_batch(task_ids))
    except LookupError as exc:
        raise NotFoundError(str(exc))
    except ValueError as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/global-previews/<task_id>", methods=["GET"])
@login_required
@_export_limit
def export_global_preview(task_id):
    task = _load_task(task_id)
    _require_completed_task(task)
    ratios = _parse_ratios_query()
    try:
        generated = export_service.export_global_preview(task["id"], ratios_override=ratios)
        export_name = request.args.get("export_name")
        if export_name:
            generated = replace(
                generated,
                filename=f"{sanitize_export_filename(export_name)}.xlsx",
            )
        return _file_response(generated)
    except (ValueError, LookupError) as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/global-previews/<task_id>/stocks", methods=["GET"])
@login_required
@_export_limit
def export_global_preview_by_stock(task_id):
    task = _load_task(task_id)
    _require_completed_task(task)
    ratios = _parse_ratios_query()
    try:
        generated = export_service.export_global_preview_by_stock(task["id"], ratios_override=ratios)
        return _stream_response(generated)
    except (ValueError, LookupError) as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/global-previews/batch", methods=["POST"])
@login_required
@_export_limit
def export_global_preview_batch():
    data = request.get_json(silent=True) or {}
    task_ids = data.get("task_ids")
    if not isinstance(task_ids, list):
        raise BadRequestError("task_ids 必须是数组")
    normalized_ids = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
    try:
        return _file_response(export_service.export_global_preview_batch(normalized_ids))
    except LookupError as exc:
        raise NotFoundError(str(exc))
    except ValueError as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/backtest-results/<int:result_id>", methods=["GET"])
@login_required
@_export_limit
def export_backtest_result(result_id):
    task_result = task_result_repository.get(result_id)
    if not task_result:
        raise NotFoundError("任务结果不存在")
    _load_task(task_result["task_id"])
    try:
        return _file_response(export_service.export_backtest_result(result_id))
    except (ValueError, LookupError) as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/xpl", methods=["POST"])
@login_required
@_export_limit
def export_xpl():
    try:
        return _file_response(export_service.export_xpl(request.get_json(silent=True) or {}))
    except ValueError as exc:
        raise BadRequestError(str(exc))


@export_api_bp.route("/backtest-reports/word", methods=["POST"])
@login_required
@_export_limit
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
        raise BadRequestError(str(exc))


@export_api_bp.route("/model-summary", methods=["GET"])
@login_required
@_export_limit
def export_model_summary():
    try:
        generated = export_service.export_model_summary(
            getattr(g, "current_user", None),
            request.args.to_dict(),
            ignore_permissions=True,
        )
        return _file_response(generated)
    except ValueError as exc:
        raise BadRequestError(str(exc))
