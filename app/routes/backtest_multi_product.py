"""Multi-product backtest pages and APIs."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
import math
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Blueprint, current_app, g, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import load_only

from app.extensions import db
from app.models import TaskResult
from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_result_return_repository import TaskResultReturnRepository
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    build_multi_product_global_preview_payload,
    normalize_multi_product_config,
)
from app.utils.c7_result_normalizer import normalize_c7_result_metrics
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type
from app.utils.return_series import parse_return_series_fields


bp = Blueprint("backtest_multi_product", __name__, url_prefix="/backtest-multi-product")
legacy_bp = Blueprint("backtest_multi_product_legacy", __name__, url_prefix="/backtest-multi")
_task_repository = TaskRepository()
_task_result_repository = TaskResultRepository()
_task_result_return_repository = TaskResultReturnRepository()

TASK_ACTION_LABELS = {
    "view": "查看",
    "create": "创建",
}

BATCH_GLOBAL_PREVIEW_EXPORT_MAX_TASKS = 10


def _sanitize_json_value(value):
    """将回测结果中的复杂值转换为 JSON 可序列化内容。"""
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _task_permission_denied(action: str, task_type: str | None, decision: dict, task_id: str | None = None):
    """构造多品回测任务权限不足时的统一接口响应。"""
    action_label = TASK_ACTION_LABELS.get(action, action)
    normalized_type = decision.get("task_type") or str(task_type or "unknown")
    missing_permissions = decision.get("missing_permissions") or []
    missing_text = "、".join(missing_permissions) if missing_permissions else "未知"
    message = f"权限不足，无法{action_label}{normalized_type}任务；当前缺少: {missing_text}"
    return jsonify({
        "status": "error",
        "message": message,
        "action": action,
        "task_type": normalized_type,
        "task_id": task_id,
        "required_permissions": decision.get("required_permissions") or [],
        "missing_permissions": missing_permissions,
    }), 403


def _load_multi_product_task_or_response(task_id: str, action: str = "view"):
    """读取多品回测任务，并在缺失或无权限时直接返回错误响应。"""
    task = _task_repository.get(task_id)
    if not task:
        return None, (jsonify({"status": "error", "message": "任务不存在"}), 404)

    decision = authorize_task_type_action(getattr(g, "current_user", None), action, task.task_type)
    if not decision["allowed"]:
        return None, _task_permission_denied(action, task.task_type, decision, task_id=task_id)

    if normalize_task_type(task.task_type) != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        return None, (jsonify({
            "status": "error",
            "message": "当前接口仅支持多品数据回测任务",
            "task_id": task_id,
            "task_type": task.task_type,
        }), 400)
    return task, None


def _parse_json(raw, default):
    """安全解析 JSON 文本；格式无效时返回调用方默认值。"""
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _infer_product_export_model_name(product):
    """从产品配置推断导出文件使用的模型名称。"""
    if not isinstance(product, dict):
        return "C3"

    sheet = product.get("sheet") or {}
    for source in (product.get("model_name"), sheet.get("title"), product.get("model_version")):
        title = str(source or "").upper()
        for model_name in ("C7", "C5", "C4", "C3"):
            if model_name in title:
                return model_name
    return "C3"


def _build_excel_download_name(task_name, fallback_id: str) -> str:
    """为单任务 Excel 导出生成安全且可读的下载文件名。"""
    safe_name = "".join(char if char not in '\\/:*?"<>|' else "_" for char in str(task_name or "").strip())
    safe_name = safe_name.rstrip(" .")
    return f"{safe_name or fallback_id}.xlsx"


def _build_zip_member_name(task_name: str | None, fallback_id: str, used_names: set[str]) -> str:
    """生成 ZIP 内唯一的 Excel 成员文件名。"""
    filename = _build_excel_download_name(task_name, fallback_id)
    if filename not in used_names:
        used_names.add(filename)
        return filename

    stem = filename[:-5]
    index = 2
    while True:
        candidate = f"{stem}_{index}.xlsx"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def _validate_batch_global_preview_task_ids(raw_task_ids):
    """校验批量全局预览导出传入的任务 ID 列表。"""
    if not isinstance(raw_task_ids, list) or not raw_task_ids:
        return None, (jsonify({"status": "error", "message": "请选择至少一个任务"}), 400)

    task_ids = [str(task_id).strip() for task_id in raw_task_ids if str(task_id).strip()]
    task_ids = list(dict.fromkeys(task_ids))
    if not task_ids:
        return None, (jsonify({"status": "error", "message": "请选择至少一个任务"}), 400)

    if len(task_ids) > BATCH_GLOBAL_PREVIEW_EXPORT_MAX_TASKS:
        return None, (jsonify({
            "status": "error",
            "message": f"批量导出最多支持 {BATCH_GLOBAL_PREVIEW_EXPORT_MAX_TASKS} 个任务，当前选择了 {len(task_ids)} 个",
        }), 400)

    return task_ids, None


def _parse_excel_percent_text(value: str) -> float | None:
    """解析 Excel 单元格中的百分比文本。"""
    text = value.strip().replace(",", "").replace("$", "")
    if not text.endswith("%"):
        return None

    sign = 1
    while text.startswith("-"):
        sign *= -1
        text = text[1:]
    try:
        number = sign * float(text[:-1]) / 100
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _format_excel_data_cell(cell):
    """为导出单元格设置文本、数值或百分比显示格式。"""
    if not isinstance(cell.value, str):
        return

    parsed = _parse_excel_percent_text(cell.value)
    if parsed is None:
        return

    cell.value = 0 if parsed == 0 else parsed
    cell.number_format = "0.00%"


@bp.route("/create")
def create_page():
    """渲染多品回测任务创建页面。"""
    return render_template("backtest_multi_product/create.html")


@bp.route("/list")
def list_page():
    """渲染多品回测任务列表页面。"""
    return render_template("backtest_multi_product/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    """渲染指定多品回测任务的详情页面。"""
    return render_template("backtest_multi_product/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    """渲染指定多品回测任务的全局预览页面。"""
    return render_template("backtest_multi_product/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    """渲染指定多品回测结果的详情页面。"""
    task_result = _task_result_repository.get(result_id)
    task_id = ""
    if task_result:
        task = _task_repository.get(task_result.get("task_id"))
        if task and normalize_task_type(task.task_type) == BACKTEST_MULTI_PRODUCT_TASK_TYPE:
            task_id = task_result.task_id
    return render_template("backtest_multi_product/result.html", result_id=result_id, task_id=task_id)


legacy_bp.add_url_rule("/create", view_func=create_page)
legacy_bp.add_url_rule("/list", view_func=list_page)
legacy_bp.add_url_rule("/detail/<task_id>", view_func=detail_page)
legacy_bp.add_url_rule("/global-preview/<task_id>", view_func=global_preview_page)
legacy_bp.add_url_rule("/result/<int:result_id>", view_func=result_page)


@bp.route("/api/import-excel", methods=["POST"])
@login_required
@permission_required("backtest:create")
def import_excel():
    """导入多品回测任务使用的 Excel 配置。"""
    excel_file = request.files.get("file")
    if not excel_file or not excel_file.filename:
        return jsonify({"status": "error", "message": "请先上传 Excel 文件"}), 400
    try:
        data = BacktestExcelService().import_uploaded_excel(excel_file)
        return jsonify({"status": "success", **_sanitize_json_value(data)})
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Failed to import multi-product backtest Excel")
        return jsonify({"status": "error", "message": f"Excel 解析失败：{exc}"}), 500


@bp.route("/api/task-results/<task_id>", methods=["GET"])
@login_required
@permission_required("backtest:view")
def get_task_results_by_task_id(task_id):
    """返回指定多品任务的结果列表，并校验查看权限。"""
    _, error_response = _load_multi_product_task_or_response(task_id, action="view")
    if error_response:
        return error_response

    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = max(min(request.args.get("per_page", default=10, type=int) or 10, 100), 1)
    pagination = (
        TaskResult.query
        .options(load_only(
            TaskResult.id,
            TaskResult.task_id,
            TaskResult.step_index,
            TaskResult.parameters,
            TaskResult.success,
            TaskResult.error_message,
            TaskResult.timestamp,
        ))
        .filter_by(task_id=task_id)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    results = [{
        "id": item.id,
        "task_id": item.task_id,
        "step_index": item.step_index,
        "parameters": _parse_json(item.parameters, {}),
        "success": item.success,
        "error_message": item.error_message,
        "timestamp": item.timestamp.isoformat() if item.timestamp else None,
    } for item in pagination.items]
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
@permission_required("backtest:view")
def get_task_result_detail(task_result_id):
    """返回一条多品回测结果的详细数据。"""
    task_result = _task_result_repository.get(task_result_id)
    if not task_result:
        return jsonify({"status": "error", "message": "任务结果不存在"}), 404
    task, error_response = _load_multi_product_task_or_response(task_result.task_id, action="view")
    if error_response:
        return error_response

    payload = _parse_json(task_result.result, {})
    if isinstance(payload, dict) and payload:
        prioritized_keys = ("calculate_metrics", "weighted_calculate_metrics", "analyze_result")
        value = next(
            (
                item
                for item in payload.values()
                if isinstance(item, dict) and any(key in item for key in prioritized_keys)
            ),
            next((item for item in payload.values() if isinstance(item, dict)), {}),
        )
    else:
        value = {}
    calculate_metrics = (
        (value.get("calculate_metrics") or value.get("analyze_result"))
        if isinstance(value, dict)
        else {}
    )
    sheet_result = {
        key: item
        for key, item in value.items()
        if key not in {"calculate_metrics", "analyze_result"}
    } if isinstance(value, dict) else {}

    daily_returns = {}
    if task_result.return_series_id:
        return_series = _task_result_return_repository.get(task_result.return_series_id)
        if return_series:
            rows = parse_return_series_fields(return_series)
            daily_returns = {
                "dates": [row["date"] for row in rows],
                "index_returns": [row.get("index_return") for row in rows],
                "start_returns": [row.get("start_return") for row in rows],
            }

    task_config = _parse_json(task.config, {})
    products = task_config.get("products") if isinstance(task_config, dict) else []
    parameters = _parse_json(task_result.parameters, {})
    product_index = parameters.get("product_index") if isinstance(parameters, dict) else None
    product = products[product_index] if isinstance(product_index, int) and 0 <= product_index < len(products) else {}
    model_name = _infer_product_export_model_name(product)
    if model_name == "C7":
        sheet_result = normalize_c7_result_metrics(sheet_result)

    return jsonify({
        "status": "success",
        "result": _sanitize_json_value({
            **(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "sheet_result": sheet_result,
            "daily_returns": daily_returns,
            "model_name": model_name,
        }),
    })


@bp.route("/api/global-preview/<task_id>", methods=["GET"])
@login_required
@permission_required("backtest:view")
def get_global_preview(task_id):
    """返回多品回测任务的全局预览数据。"""
    _, error_response = _load_multi_product_task_or_response(task_id, action="view")
    if error_response:
        return error_response
    payload = build_multi_product_global_preview_payload(task_id)
    if payload is None:
        return jsonify({"status": "error", "message": "任务不存在"}), 404
    return jsonify({"status": "success", **_sanitize_json_value(payload)})


@bp.route("/api/global-preview/<task_id>/calculate-ratios", methods=["POST"])
@login_required
@permission_required("backtest:view")
def calculate_ratios(task_id):
    """根据任务当前产品配置计算建议比例。"""
    _, error_response = _load_multi_product_task_or_response(task_id, action="view")
    if error_response:
        return error_response
    data = request.get_json() or {}
    ratios = data.get("ratios")
    if not isinstance(ratios, list):
        return jsonify({"status": "error", "message": "ratios 必须是数组"}), 400
    try:
        payload = build_multi_product_global_preview_payload(task_id, ratios_override=ratios)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if payload is None:
        return jsonify({"status": "error", "message": "任务不存在"}), 404
    return jsonify({"status": "success", **_sanitize_json_value(payload)})


@bp.route("/api/global-preview/<task_id>/ratios", methods=["PUT"])
@login_required
@permission_required("backtest:create")
def update_ratios(task_id):
    """更新多品回测任务中各产品的比例配置。"""
    task, error_response = _load_multi_product_task_or_response(task_id, action="create")
    if error_response:
        return error_response
    data = request.get_json() or {}
    ratios = data.get("ratios")
    if not isinstance(ratios, list):
        return jsonify({"status": "error", "message": "ratios 必须是数组"}), 400

    config = normalize_multi_product_config(task.to_dict().get("config") or {})
    products = config["products"]
    if len(ratios) != len(products):
        return jsonify({"status": "error", "message": "比例数量与产品数量不一致"}), 400
    for product, ratio in zip(products, ratios):
        product["ratio"] = str(ratio.get("ratio") if isinstance(ratio, dict) else ratio).strip()
    try:
        config = normalize_multi_product_config({**config, "products": products})
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    _task_repository.save({**task.to_dict(), "config": config})
    payload = build_multi_product_global_preview_payload(task_id)
    return jsonify({"status": "success", "message": "比例已保存", **_sanitize_json_value(payload or {})})


def _build_global_preview_workbook(payload: dict[str, object]):
    """将多品回测全局预览载荷转换为 Excel 工作簿。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "多品全局预览"
    header_fill = PatternFill("solid", fgColor="F7E1A1")
    sub_header_fill = PatternFill("solid", fgColor="FCECC5")
    first_col_fill = PatternFill("solid", fgColor="F7E1A1")
    thin_side = Side(style="thin", color="D0D0D0")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center = Alignment(horizontal="center", vertical="center")
    header_font = Font(name="Microsoft YaHei", size=11, bold=True)
    body_font = Font(name="Microsoft YaHei", size=10)

    products = payload.get("products") or []
    total_columns = max(4, 2 + len(products) * 3 + 2)
    last_column = get_column_letter(total_columns)

    for group in payload.get("groups") or []:
        group_header = ["", ""]
        for product in products:
            group_header.extend([product.get("product_name") or product.get("stock_code") or "产品", "", ""])
        group_header.extend(["", ""])
        sheet.append(group_header[:total_columns])
        group_title_row = sheet.max_row

        current_column = 3
        for _product in products:
            sheet.merge_cells(
                start_row=group_title_row,
                start_column=current_column,
                end_row=group_title_row,
                end_column=current_column + 2,
            )
            current_column += 3

        header = ["指标类型", "指标"]
        for product in products:
            ratio = product.get("ratio")
            header.extend(["指数", "模型结果", f"模型结果（{ratio}%）"])
        header.extend(["比例计算-指数", "比例计算-结果"])
        sheet.append(header)
        for row in group.get("rows") or []:
            values = [row.get("category") or "", row.get("metric") or ""]
            for product_value in row.get("product_values") or []:
                values.extend([
                    product_value.get("index_value") or "-",
                    product_value.get("result_value") or "-",
                    product_value.get("weighted_result_value") or "-",
                ])
            values.extend([
                row.get("weighted_index_value") or "-",
                row.get("weighted_result_value") or "-",
            ])
            sheet.append(values)
        sheet.append([""] * total_columns)

    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = center
            cell.border = thin_border
            cell.font = body_font
            if cell.row == 1:
                cell.fill = sub_header_fill
                cell.font = header_font
            if cell.value in {
                "指标类型",
                "指标",
                "指数",
                "模型结果",
                "比例计算-指数",
                "比例计算-结果",
            } or str(cell.value or "").startswith("模型结果（"):
                cell.font = header_font
                cell.fill = sub_header_fill
            if cell.column == 1:
                cell.fill = first_col_fill
                if cell.row <= 2:
                    cell.font = header_font
            if cell.row >= 3 and cell.column >= 3:
                _format_excel_data_cell(cell)
    for column_index in range(1, total_columns + 1):
        sheet.column_dimensions[get_column_letter(column_index)].width = 18 if column_index > 2 else 16
    sheet.freeze_panes = "A3"
    if sheet.max_row >= 2:
        sheet.auto_filter.ref = f"A2:{last_column}{sheet.max_row}"
    return workbook


@bp.route("/api/global-preview/<task_id>/export", methods=["GET"])
@login_required
@permission_required("backtest:view")
def export_global_preview(task_id):
    """导出单个多品回测任务的全局预览工作簿。"""
    _, error_response = _load_multi_product_task_or_response(task_id, action="view")
    if error_response:
        return error_response
    ratios = None
    raw_ratios = request.args.get("ratios")
    if raw_ratios:
        try:
            ratios = json.loads(raw_ratios)
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "ratios 参数不是有效 JSON"}), 400
    try:
        payload = build_multi_product_global_preview_payload(task_id, ratios_override=ratios)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if payload is None:
        return jsonify({"status": "error", "message": "任务不存在"}), 404

    workbook = _build_global_preview_workbook(payload)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    task_name = (payload.get("task") or {}).get("name") or task_id
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=_build_excel_download_name(task_name, task_id),
    )


@bp.route("/api/global-preview/batch-export", methods=["POST"])
@login_required
@permission_required("backtest:view")
def batch_export_global_preview():
    """将多个多品回测任务的预览工作簿打包导出。"""
    data = request.get_json(silent=True) or {}
    task_ids, error_response = _validate_batch_global_preview_task_ids(data.get("task_ids"))
    if error_response:
        return error_response

    zip_buffer = BytesIO()
    used_names: set[str] = set()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as archive:
        for task_id in task_ids:
            task, task_error_response = _load_multi_product_task_or_response(task_id, action="view")
            if task_error_response:
                return task_error_response
            if task.status != "completed":
                return jsonify({
                    "status": "error",
                    "message": f"任务 {task.name or task_id} 尚未完成，不能导出",
                    "task_id": task_id,
                    "task_status": task.status,
                }), 400

            payload = build_multi_product_global_preview_payload(task_id)
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
        download_name=f"backtest_multi_product_global_preview_batch_{stamp}.zip",
    )
