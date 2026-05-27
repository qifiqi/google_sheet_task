"""Multi-product backtest pages and APIs."""

from __future__ import annotations

from io import BytesIO
import json
import re

from flask import Blueprint, current_app, g, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import load_only

from app.extensions import db
from app.models import Task, TaskResult
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    build_multi_product_global_preview_payload,
    normalize_multi_product_config,
)
from app.utils.auth import login_required, permission_required
from app.utils.dfcf_api import DFCJStockApi
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type


bp = Blueprint("backtest_multi_product", __name__, url_prefix="/backtest-multi-product")
legacy_bp = Blueprint("backtest_multi_product_legacy", __name__, url_prefix="/backtest-multi")

TASK_ACTION_LABELS = {
    "view": "查看",
    "create": "创建",
}


def _sanitize_json_value(value):
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _strip_html_tags(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _task_permission_denied(action: str, task_type: str | None, decision: dict, task_id: str | None = None):
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
    task = db.session.get(Task, task_id)
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
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _build_excel_download_name(task_name, fallback_id: str) -> str:
    safe_name = "".join(char if char not in '\\/:*?"<>|' else "_" for char in str(task_name or "").strip())
    safe_name = safe_name.rstrip(" .")
    return f"{safe_name or fallback_id}.xlsx"


@bp.route("/create")
def create_page():
    return render_template("backtest_multi_product/create.html")


@bp.route("/list")
def list_page():
    return render_template("backtest_multi_product/list.html")


@bp.route("/detail/<task_id>")
def detail_page(task_id):
    return render_template("backtest_multi_product/detail.html", task_id=task_id)


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    return render_template("backtest_multi_product/global_preview.html", task_id=task_id)


@bp.route("/result/<int:result_id>")
def result_page(result_id):
    task_result = db.session.get(TaskResult, result_id)
    task_id = ""
    if task_result and task_result.task and normalize_task_type(task_result.task.task_type) == BACKTEST_MULTI_PRODUCT_TASK_TYPE:
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


@bp.route("/api/search-stocks", methods=["GET"])
@login_required
@permission_required("backtest:view")
def search_stocks():
    keyword = (request.args.get("q") or "").strip()
    page_size = request.args.get("page_size", default=10, type=int) or 10
    page_size = max(1, min(page_size, 20))
    if len(keyword) < 1:
        return jsonify({"status": "success", "keyword": keyword, "results": []})

    raw_results = DFCJStockApi().get_search_list_by_stock_code(keyword, page_size=page_size)
    if isinstance(raw_results, dict) and raw_results.get("error"):
        return jsonify({"status": "error", "message": raw_results.get("error") or "股票搜索失败"}), 502

    normalized_results = []
    for item in raw_results or []:
        if item.get("status") not in (10, "10", None):
            continue
        code = _strip_html_tags(item.get("code"))
        short_name = _strip_html_tags(item.get("shortName"))
        security_type_name = _strip_html_tags(item.get("securityTypeName"))
        if not code:
            continue
        normalized_results.append({
            "source": item.get("source"),
            "code": code,
            "name": short_name,
            "security_type_name": security_type_name,
            "market": item.get("market"),
            "label": " · ".join(part for part in [code, short_name, security_type_name] if part),
            "status": item.get("status"),
        })

    return jsonify({"status": "success", "keyword": keyword, "results": normalized_results})


@bp.route("/api/task-results/<task_id>", methods=["GET"])
@login_required
@permission_required("backtest:view")
def get_task_results_by_task_id(task_id):
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
    task_result = db.session.get(TaskResult, task_result_id)
    if not task_result:
        return jsonify({"status": "error", "message": "任务结果不存在"}), 404
    _, error_response = _load_multi_product_task_or_response(task_result.task_id, action="view")
    if error_response:
        return error_response

    payload = _parse_json(task_result.result, {})
    if isinstance(payload, dict) and payload:
        prioritized_keys = ("calculate_metrics", "weighted_calculate_metrics")
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
    calculate_metrics = value.get("calculate_metrics") if isinstance(value, dict) else {}
    sheet_result = {
        key: item for key, item in value.items() if key != "calculate_metrics"
    } if isinstance(value, dict) else {}
    return jsonify({
        "status": "success",
        "result": _sanitize_json_value({
            **(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "sheet_result": sheet_result,
        }),
    })


@bp.route("/api/global-preview/<task_id>", methods=["GET"])
@login_required
@permission_required("backtest:view")
def get_global_preview(task_id):
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

    task.config = json.dumps(config, ensure_ascii=False)
    db.session.commit()
    payload = build_multi_product_global_preview_payload(task_id)
    return jsonify({"status": "success", "message": "比例已保存", **_sanitize_json_value(payload or {})})


def _build_global_preview_workbook(payload: dict[str, object]):
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
            header.extend(["指数", "模型结果", "单品比例参考"])
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
                "单品比例参考",
                "比例计算-指数",
                "比例计算-结果",
            }:
                cell.font = header_font
                cell.fill = sub_header_fill
            if cell.column == 1:
                cell.fill = first_col_fill
                if cell.row <= 2:
                    cell.font = header_font
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
