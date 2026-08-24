"""Standalone global preview entry for C-series backtest tasks."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from queue import Queue
from threading import Thread
from time import perf_counter
from urllib.parse import quote
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from flask import Blueprint, Response, current_app, g, jsonify, render_template, request, send_file, stream_with_context

from app.extensions import db
from app.models import Task
from app.services.backtest_training_api_service import (
    _build_global_preview_payload,
    _build_global_preview_group_payload,
    _build_global_preview_initial_payload,
    _build_global_preview_workbook,
    get_global_preview_result_ids_by_stock,
    split_global_preview_payload_by_stock,
)
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type


bp = Blueprint("global_preview", __name__, url_prefix="/global-preview")


def _task_error(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code


def _safe_filename(value, fallback):
    cleaned = "".join(char if char not in '\\/:*?\"<>|' else "_" for char in str(value or "").strip())
    return cleaned.rstrip(" .") or fallback


def _load_backtest_task_or_response(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return None, _task_error("任务不存在", 404)

    decision = authorize_task_type_action(getattr(g, "current_user", None), "view", task.task_type)
    if not decision["allowed"]:
        missing_permissions = "、".join(decision.get("missing_permissions") or []) or "未知"
        return None, _task_error(f"权限不足，当前缺少: {missing_permissions}", 403)

    return task, None


def _preview_status(task):
    task_type = normalize_task_type(task.task_type)
    if task_type in {
        "backtest_training",
        "google_sheet",
        "google_sheet_c4",
        "google_sheet_c5",
        "google_sheet_c7",
    }:
        return {"supported": True, "message": "C 系列单品回测全局预览已就绪"}
    if task_type == "backtest_multi_product":
        return {"supported": False, "message": "多品回测入口已预留，内容将在后续适配"}
    return {"supported": False, "message": "当前任务类型暂不支持全局预览"}


@bp.route("")
@bp.route("/single_product")
def page():
    return render_template("global_preview/index.html")


@bp.route("/api/tasks/<task_id>", methods=["GET"])
@login_required
@permission_required("backtest:view")
def get_preview(task_id):
    task, error_response = _load_backtest_task_or_response(task_id)
    if error_response:
        return error_response

    status = _preview_status(task)
    response = {
        "status": "success",
        "task": {"id": task.id, "name": task.name, "task_type": task.task_type, "task_status": task.status},
        **status,
    }
    if status["supported"]:
        initial = _build_global_preview_initial_payload(task_id)
        response["initial"] = initial
        # 保留 preview 字段，避免已有调用方在前端升级期间失效。
        response["preview"] = initial["preview"]
    return jsonify(response)


@bp.route("/api/tasks/<task_id>/preview-group", methods=["POST"])
@login_required
@permission_required("backtest:view")
def get_preview_group(task_id):
    task, error_response = _load_backtest_task_or_response(task_id)
    if error_response:
        return error_response
    if not _preview_status(task)["supported"]:
        return _task_error("当前任务暂不支持全局预览", 400)

    # result_ids 来自初始化接口；服务层仍会附加 task_id 条件，防止跨任务读取。
    result_ids = (request.get_json(silent=True) or {}).get("result_ids") or []
    if not isinstance(result_ids, list) or not result_ids:
        return _task_error("请选择需要加载的结果分组", 400)
    payload = _build_global_preview_group_payload(task_id, result_ids)
    return jsonify({"status": "success", "preview": payload})


class _ZipStreamWriter:
    """将 ZipFile 写出的字节块放入队列，供 Flask 逐块响应给浏览器。"""

    def __init__(self, output_queue):
        self.output_queue = output_queue
        self.position = 0

    def write(self, data):
        if data:
            self.output_queue.put(bytes(data))
            self.position += len(data)
        return len(data)

    def tell(self):
        return self.position

    def flush(self):
        return None

    def writable(self):
        return True


def _stream_stock_export_zip(task_id, task_name):
    """一次读取任务全部结果，内存分股票后逐个生成 Excel 并流式写 ZIP。"""
    output_queue = Queue(maxsize=8)
    finished = object()
    flask_app = current_app._get_current_object()

    def produce():
        try:
            with flask_app.app_context():
                export_started_at = perf_counter()
                # 导出全量文件时一次取完结果，避免按股票反复访问数据库。
                # 仅 Excel 按股票逐个生成，避免同时持有多个工作簿。
                payload = _build_global_preview_payload(task_id)
                stock_payloads = sorted(
                    split_global_preview_payload_by_stock(payload or {}),
                    key=lambda item: item[0],
                )
                # xlsx 本身就是压缩格式；外层不再重复 Deflate，显著减少 CPU 时间。
                with ZipFile(_ZipStreamWriter(output_queue), "w", ZIP_STORED) as archive:
                    for stock_code, stock_payload in stock_payloads:
                        stock_started_at = perf_counter()
                        workbook = _build_global_preview_workbook(stock_payload)
                        filename = f"{_safe_filename(f'{task_name}_{stock_code}', stock_code)}.xlsx"
                        # 显式设置 ZIP 条目时间，Windows 解压后会以此作为 Excel 修改时间。
                        # 仍直接写入 ZIP 条目，避免每支股票额外保留一份 xlsx 字节副本。
                        zip_info = ZipInfo(filename, date_time=datetime.now().timetuple()[:6])
                        zip_info.compress_type = ZIP_STORED
                        with archive.open(zip_info, "w") as xlsx_file:
                            workbook.save(xlsx_file)
                        flask_app.logger.info(
                            "全局预览导出单股票完成: task_id=%s stock=%s results=%s elapsed=%.2fs",
                            task_id, stock_code,
                            (stock_payload.get("summary") or {}).get("total_results", 0),
                            perf_counter() - stock_started_at,
                        )
                flask_app.logger.info(
                    "全局预览流式导出完成: task_id=%s stocks=%s elapsed=%.2fs",
                    task_id, len(stock_payloads), perf_counter() - export_started_at,
                )
        except Exception:
            flask_app.logger.exception("全局预览流式导出失败: task_id=%s", task_id)
        finally:
            output_queue.put(finished)

    Thread(target=produce, daemon=True).start()

    @stream_with_context
    def generate():
        while True:
            chunk = output_queue.get()
            if chunk is finished:
                break
            yield chunk

    return generate()


@bp.route("/api/tasks/<task_id>/export", methods=["GET"])
@login_required
@permission_required("backtest:view")
def export_preview(task_id):
    task, error_response = _load_backtest_task_or_response(task_id)
    if error_response:
        return error_response
    if not _preview_status(task)["supported"]:
        return _task_error("当前任务暂未适配全局预览导出", 400)

    _task_for_export, stock_groups = get_global_preview_result_ids_by_stock(task_id)
    if not stock_groups:
        return _task_error("任务暂无可导出的结果", 400)

    task_name = _safe_filename(request.args.get("export_name"), _safe_filename(task.name, task_id))
    if len(stock_groups) == 1:
        # 单股票直接按该任务所有结果生成一个 Excel。
        workbook = _build_global_preview_workbook(
            _build_global_preview_payload(task_id)
        )
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{task_name}.xlsx",
        )

    return Response(
        _stream_stock_export_zip(task_id, task_name),
        mimetype="application/zip",
        headers={
            "Content-Disposition": (
                "attachment; filename=global-preview.zip; "
                f"filename*=UTF-8''{quote(f'{task_name}.zip')}"
            )
        },
    )
