"""任务 API（数据层：task_repository / task_result_repository）。

说明：
- create/start/restart/update-config 等执行链响应由 task_manager 服务层构造
  （task/creation、task/restart 属 B3 范围），路由保持透传；
- 服务层仍以 ValueError 表达请求校验失败（400 语义），本层显式翻译为
  BadRequestError，待 B3 服务层改抛语义异常后移除。
"""
import csv
import json
import time
from datetime import datetime
from io import BytesIO

from flask import Blueprint, g, jsonify, request, send_file

from app.exceptions import BadRequestError, NotFoundError
from app.schemas.task import TaskCreateSchema, TasksBatchCreateSchema, TaskRestartSchema
from app.repositories import task_repository, task_result_repository
from app.services.export_file_service import (
    EXCEL_MIMETYPE,
    BatchExportFile,
    build_batch_export_file,
    build_c7_stock_code_export_archive,
    build_c3_worksheets,
    build_task_export,
    build_workbook,
    sanitize_export_filename,
)
from app.services.task import TaskRuntimeViewService, task_manager
from app.utils.api_response import error, success
from app.utils.request_parsing import parse_body
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

task_api_bp = Blueprint('task_api', __name__)
runtime_view_service = TaskRuntimeViewService(task_manager)


def _get_task_entity_or_404(task_id: str):
    """任务实体访问（导出/执行链消费实体）；不存在抛 NotFoundError。"""
    task = task_repository.get_entity(task_id)
    if not task:
        raise NotFoundError("任务不存在")
    return task


@task_api_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """获取任务列表 / 创建任务"""
    if request.method == 'GET':
        task_type = request.args.get('task_type')
        page = request.args.get('page', type=int)
        per_page = request.args.get('per_page', type=int)
        task_status = request.args.get('status')
        keyword = request.args.get('keyword', '', type=str)
        allowed_task_types = None

        if not task_type:
            allowed_task_types = task_repository.distinct_task_types()

        default_page = page or 1
        default_per_page = per_page or 10

        if not task_type and not allowed_task_types:
            return success(data={
                "tasks": [],
                "pagination": {
                    "page": default_page,
                    "per_page": default_per_page,
                    "total": 0,
                    "pages": 0,
                    "has_prev": False,
                    "has_next": False,
                    "prev_num": None,
                    "next_num": None,
                },
                "statistics": {
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "running_tasks": 0,
                    "error_tasks": 0,
                    "pending_tasks": 0,
                    "today_new_tasks": 0,
                    "success_rate": 0,
                    "error_rate": 0,
                    "avg_duration_minutes": 0,
                },
            })

        data = task_manager.get_tasks_paginated(
            page=default_page,
            per_page=default_per_page,
            task_type=task_type,
            task_types=allowed_task_types if not task_type else None,
            status=task_status,
            keyword=keyword,
        )
        return success(data={
            "tasks": data["tasks"],
            "pagination": data["pagination"],
            "statistics": data["statistics"],
        })

    data = parse_body(TaskCreateSchema)
    current_user = getattr(g, "current_user", None)
    response, status_code = task_manager.create_and_start_task(
        data.name,
        data.description,
        data.task_type,
        data.config,
        created_by_user_id=getattr(current_user, "id", None),
    )
    return jsonify(response), status_code


@task_api_bp.route('/tasks/batch-create', methods=['POST'])
@login_required
def batch_create_tasks():
    """C31 批量创建接口"""
    data = parse_body(TasksBatchCreateSchema).root
    logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

    response, status_code = task_manager.batch_create_and_start_task(
        data,
        created_by_user_id=getattr(getattr(g, "current_user", None), "id", None),
    )
    if status_code == 200:
        response["debug_message"] = "已调用原有 C3 创建流程；当前仍为占位版批量接口"
    return jsonify(response), status_code


@task_api_bp.route('/tasks/<task_id>', methods=['GET', 'DELETE'])
@login_required
def task_detail(task_id):
    """获取/删除任务详情"""
    _get_task_entity_or_404(task_id)

    if request.method == 'GET':
        task = task_manager.get_task_status(task_id)
        if not task:
            raise NotFoundError("任务不存在")
        return success(data={"task": task})

    deleted = task_manager.delete_task(task_id)
    if deleted:
        return success(message="任务已删除")
    raise BadRequestError("删除任务失败")


@task_api_bp.route('/tasks/<task_id>/config', methods=['PUT'])
@login_required
def update_task_config(task_id):
    """更新任务配置"""
    _get_task_entity_or_404(task_id)

    data = request.get_json()
    if not data:
        raise BadRequestError("请求数据为空")

    config = data.get('config')
    if not config:
        raise BadRequestError("配置信息不能为空")

    result = task_manager.update_task_config(
        task_id,
        config,
        data.get('name'),
        data.get('description'),
        data.get('status'),
    )

    if result["status"] == "success":
        return jsonify(result)
    return jsonify(result), 400


@task_api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """取消任务"""
    _get_task_entity_or_404(task_id)

    cancelled = task_manager.cancel_task(task_id)
    if cancelled:
        return success(message="任务已取消")
    raise BadRequestError("取消任务失败")


@task_api_bp.route('/tasks/<task_id>/logs', methods=['GET'])
@login_required
def get_task_logs(task_id):
    """获取任务日志"""
    _get_task_entity_or_404(task_id)

    logs = task_manager.get_task_logs(task_id)
    return success(data={"logs": logs})


@task_api_bp.route('/tasks/<task_id>/results', methods=['GET'])
@login_required
def get_task_results(task_id):
    """获取任务结果"""
    _get_task_entity_or_404(task_id)

    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)

    if page is not None and per_page is not None:
        data = task_manager.get_task_results(task_id, page=page, per_page=per_page)
        return success(data={
            "results": data["items"],
            "total": data["total"],
            "pages": data["pages"],
            "current_page": data["current_page"],
            "per_page": data["per_page"],
            "total_success": data.get("total_success"),
            "total_failed": data.get("total_failed"),
        })

    results = task_manager.get_task_results(task_id)
    return success(data={"results": results})


def export_task_results(task_id):
    """导出任务结果。"""
    task_obj = _get_task_entity_or_404(task_id)

    try:
        results = task_manager.get_task_results(task_id)
        export_file = build_task_export(task_obj, results)
        buffer = BytesIO()
        export_file.workbook.save(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype=export_file.mimetype,
            as_attachment=True,
            download_name=export_file.filename,
        )
    except ValueError as e:
        logger.warning(f"导出任务结果校验失败: {str(e)}")
        raise BadRequestError(str(e))


def export_c7_results_by_stock_code(task_id):
    """按股票代码拆分 C7 结果，并以 ZIP 文件下载。"""
    task_obj = _get_task_entity_or_404(task_id)

    try:
        results = task_manager.get_task_results(task_id)
        export_file = build_c7_stock_code_export_archive(task_obj, results)
        return send_file(
            export_file.buffer,
            mimetype=export_file.mimetype,
            as_attachment=True,
            download_name=export_file.filename,
        )
    except ValueError as e:
        logger.warning("按股票代码导出任务结果校验失败 task_id=%s: %s", task_id, e)
        raise BadRequestError(str(e))


# ── 批量导出配置 ───────────────────────────────────────────────
# 单次合并导出允许的最大任务数；超过此值直接拒绝请求，
# 避免单次生成过大的 Excel 导致内存压力和响应超时。
BATCH_EXPORT_MAX_TASKS = 10


def batch_export_task_results():
    """批量合并导出多个 C3 任务结果。

    流程概览：
      1. 参数校验（数量上限、任务存在性、用户权限）
      2. 一次 SQL 批量查询所有 TaskResult（替代原来的 N+1 循环）
      3. 按 task_name 排序后组装 merged_results
      4. 调用 build_c3_worksheets 生成导出行
      5. 返回带 Content-Length 的 send_file 响应（前端可展示进度条）

    请求体: {"task_ids": ["id1", "id2", ...]}
    最多支持 BATCH_EXPORT_MAX_TASKS 个任务，超出返回 400。
    """
    try:
        _t_total = time.time()

        # ① 参数校验：至少一个任务且不超过上限
        data = request.get_json() or {}
        task_ids = data.get('task_ids', [])

        if not task_ids or not isinstance(task_ids, list):
            raise BadRequestError("请选择至少一个任务")

        if len(task_ids) > BATCH_EXPORT_MAX_TASKS:
            raise BadRequestError(
                f"合并导出最多支持 {BATCH_EXPORT_MAX_TASKS} 个任务，当前选择了 {len(task_ids)} 个"
            )

        # ② 查询任务并逐条校验存在性
        tasks = task_repository.list_by_ids(task_ids)
        if not tasks:
            raise NotFoundError("未找到匹配任务")

        # ③ 批量查询 TaskResult 导出投影
        #    只选择导出需要的列（task_id, step_index, result），跳过 parameters（巨大JSON，
        #    包含 kline 数据，单行 ~10KB）、return_series_id、error_message、timestamp 等无关列。
        #    导出场景数据量大（~100MB/万行），避免读取无关的大字段。
        _t_query = time.time()
        raw_rows = task_result_repository.list_export_rows(task_ids)
        logger.info(f"[batch-export] DB query: {time.time()-_t_query:.2f}s, {len(raw_rows)} rows")

        # ④ 按 task_name 排序后组装 merged_results
        #    将原始行转为导出所需的 dict 格式（不含 parameters，kline_range 默认为 "-"）
        tasks.sort(key=lambda t: t["name"] or "")
        result_map: dict[str, list] = {}
        for row in raw_rows:
            parsed_result = json.loads(row["result"]) if row["result"] else {}
            result_map.setdefault(row["task_id"], []).append({
                "task_id": row["task_id"],
                "step_index": row["step_index"],
                "result": parsed_result,
            })

        merged_results = []
        for t in tasks:
            task_name = t["name"] or ""
            for r in result_map.get(t["id"], []):
                r["task_name"] = task_name
                merged_results.append(r)

        # ⑤ CSV 导出（当前使用，性能优先）
        _t_excel = time.time()
        worksheets = build_c3_worksheets(merged_results)

        from io import StringIO
        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        if worksheets:
            writer.writerow(worksheets[0].header)
            for ws in worksheets:
                writer.writerows(ws.rows)

        csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")
        csv_buffer = BytesIO(csv_bytes)
        csv_buffer.seek(0)
        csv_size = len(csv_bytes)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = sanitize_export_filename(f"C3_合并导出_{stamp}") + ".csv"
        logger.info(f"[batch-export] CSV build: {time.time()-_t_excel:.2f}s, {csv_size/1024/1024:.2f}MB")

        response = send_file(
            csv_buffer,
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=csv_filename,
        )
        response.headers['Content-Length'] = csv_size
        logger.info(f"[batch-export] Total: {time.time()-_t_total:.2f}s")
        return response

        # ── xlsxwriter Excel 导出（备用，切换时取消注释并注释上方 CSV 部分） ──
        # _t_excel = time.time()
        # import xlsxwriter
        # worksheets = build_c3_worksheets(merged_results)
        # stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # filename = sanitize_export_filename(f"C3_合并导出_{stamp}") + ".xlsx"
        # buf = BytesIO()
        # wb = xlsxwriter.Workbook(buf, {"in_memory": True, "constant_memory": True})
        #
        # # 预定义格式
        # header_fmt = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
        # num_fmt    = wb.add_format({"num_format": "0.00"})
        # pct_fmt    = wb.add_format({"num_format": "0.00"})
        # default_fmt = wb.add_format()
        #
        # from app.services.export_file_service import (
        #     C3_EXPORT_COLUMNS, C3_NUMBER_COLUMN_NAMES, c3_display_header,
        # )
        # display_header = c3_display_header(C3_EXPORT_COLUMNS)
        # col_format_map = {name: num_fmt for name in C3_NUMBER_COLUMN_NAMES}
        #
        # for ws_data in worksheets:
        #     ws = wb.add_worksheet(ws_data.name[:31])
        #     # 表头
        #     for col_idx, hdr in enumerate(display_header):
        #         ws.write(0, col_idx, hdr, header_fmt)
        #     # 数据行
        #     for row_idx, row in enumerate(ws_data.rows, start=1):
        #         for col_idx, val in enumerate(row):
        #             col_name = C3_EXPORT_COLUMNS[col_idx] if col_idx < len(C3_EXPORT_COLUMNS) else ""
        #             fmt = col_format_map.get(col_name, default_fmt)
        #             ws.write(row_idx, col_idx, val if val != "" else None, fmt)
        #     # 列宽
        #     for col_idx, col_name in enumerate(C3_EXPORT_COLUMNS):
        #         from app.services.export_file_service import C3_COLUMN_WIDTHS
        #         width = C3_COLUMN_WIDTHS.get(col_name, 12)
        #         ws.set_column(col_idx, col_idx, width)
        #
        # wb.close()
        # buf.seek(0)
        # file_size = buf.getbuffer().nbytes
        # logger.info(f"[batch-export] xlsxwriter build: {time.time()-_t_excel:.2f}s, {file_size/1024/1024:.2f}MB")
        #
        # response = send_file(
        #     buf,
        #     mimetype=EXCEL_MIMETYPE,
        #     as_attachment=True,
        #     download_name=filename,
        # )
        # response.headers['Content-Length'] = file_size
        # logger.info(f"[batch-export] Total: {time.time()-_t_total:.2f}s")
        # return response

        # ── openpyxl Excel 导出（原始方案，已弃用） ──
        # _t_excel = time.time()
        # export_file: BatchExportFile = build_batch_export_file(merged_results)
        # logger.info(f"[batch-export] Excel build: {time.time()-_t_excel:.2f}s, {export_file.file_size/1024/1024:.2f}MB")
        # response = send_file(
        #     export_file.buffer,
        #     mimetype=EXCEL_MIMETYPE,
        #     as_attachment=True,
        #     download_name=export_file.filename,
        # )
        # response.headers['Content-Length'] = export_file.file_size
        # logger.info(f"[batch-export] Total: {time.time()-_t_total:.2f}s")
        # return response

    except ValueError as e:
        # 业务校验失败（如 merged_results 为空）
        logger.warning(f"批量导出校验失败: {str(e)}")
        raise BadRequestError(str(e))


@task_api_bp.route('/tasks/<task_id>/status-check', methods=['GET'])
@login_required
def check_task_status(task_id):
    """检查任务本地状态"""
    _get_task_entity_or_404(task_id)

    status_check = task_manager.check_local_task_status(task_id)
    return success(data={"status_check": status_check})


@task_api_bp.route('/tasks/<task_id>/stop-confirmation', methods=['GET'])
@login_required
def get_task_stop_confirmation(task_id):
    """确认任务是否已经完全停止"""
    _get_task_entity_or_404(task_id)

    stop_confirmation = runtime_view_service.build_stop_confirmation(task_id)

    return success(data=stop_confirmation)


@task_api_bp.route('/tasks/<task_id>/restart', methods=['POST'])
@login_required
def restart_task(task_id):
    """重启任务"""
    _get_task_entity_or_404(task_id)

    data = parse_body(TaskRestartSchema)

    result = task_manager.restart_task(task_id, data.resume_from_checkpoint)
    if result["status"] == "success":
        return jsonify(result)
    return jsonify(result), 400


@task_api_bp.route('/tasks/<task_id>/create-restart', methods=['POST'])
@login_required
def create_restart_task_api(task_id):
    """基于原任务创建新的重启任务"""
    task_obj = _get_task_entity_or_404(task_id)

    new_task_id = task_manager.create_restart_task(task_id)

    if task_manager.start_task(new_task_id):
        return success(
            data={"new_task_id": new_task_id},
            message="重启任务创建并启动成功",
        )
    start_error = task_manager.get_start_error(new_task_id)
    if task_obj.task_type in ("backtest_training", "backtest_multi_product") and "已有回测任务正在运行" in start_error:
        return success(
            data={"new_task_id": new_task_id, "queued": True},
            message=start_error,
        )
    return error(
        f"重启任务创建成功，但启动失败: {start_error}",
        http_status=400,
        data={"new_task_id": new_task_id, "start_error": start_error},
    )


@task_api_bp.route('/tasks/<task_id>/system-logs', methods=['GET'])
@login_required
def get_task_system_logs(task_id):
    """获取任务相关的系统日志"""
    _get_task_entity_or_404(task_id)

    import os
    import re
    from app.config import Config

    limit = request.args.get('limit', 200, type=int)
    level_filter = request.args.get('level', '')

    log_file = Config.LOG_FILE
    task_logs = []

    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'
            task_patterns = [f"[Task-{task_id[:8]}]", f"任务 {task_id}", task_id]

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                contains_task_info = any(pattern in line for pattern in task_patterns)
                if not contains_task_info:
                    continue

                match = re.match(log_pattern, line)
                if match:
                    timestamp_str, source, level, message = match.groups()

                    try:
                        from datetime import datetime
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        iso_timestamp = timestamp.isoformat()
                    except Exception:
                        iso_timestamp = timestamp_str

                    log_entry = {
                        'timestamp': iso_timestamp,
                        'level': level.lower(),
                        'message': message.strip(),
                        'source': source.strip(),
                        'task_id': task_id
                    }

                    if level_filter and log_entry['level'] != level_filter.lower():
                        continue

                    task_logs.append(log_entry)

            task_logs.sort(key=lambda x: x['timestamp'])
            task_logs = task_logs[-limit:]

    return success(data={
        "logs": task_logs,
        "task_id": task_id,
        "total_found": len(task_logs),
    })
