# -*- coding: utf-8 -*-
"""Backtest training page routes."""

import json
import math
from collections import OrderedDict
from io import BytesIO

from flask import Blueprint, jsonify, render_template, request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import load_only

from app.models import Task, TaskResult
from app.services.xpl_service import xpl_analyzer

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


@bp.route("/global-preview/<task_id>")
def global_preview_page(task_id):
    return render_template("backtest_training/global_preview.html", task_id=task_id)


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


def _build_parameter_header(parameters):
    parameter_values = parameters.get("parameter")
    if not isinstance(parameter_values, list) or not parameter_values:
        return "未命名参数"

    if len(parameter_values) == 2:
        labels = ["xm", "ml"]
    else:
        labels = [f"参数{i + 1}" for i in range(len(parameter_values))]

    parts = []
    for _, value in zip(labels, parameter_values):
        parts.append(f"{value}")
    return " / ".join(parts)


def _extract_result_core(task_result):
    payload = task_result.to_dict().get("result") or {}
    if not isinstance(payload, dict) or not payload:
        return {}
    first_value = next(iter(payload.values()), {})
    return first_value if isinstance(first_value, dict) else {}


def _detect_model_name(task_name, parameters):
    upper_name = (task_name or "").upper()
    for model_name in ("C5", "C4", "C3"):
        if model_name in upper_name:
            return model_name

    parameter_values = parameters.get("parameter")
    if isinstance(parameter_values, list) and len(parameter_values) == 2:
        return "C5"
    return "C3"


def _extract_summary_rows(calculate_metrics, model_name):
    if not isinstance(calculate_metrics, dict) or not calculate_metrics:
        return "", []

    try:
        summary_df = xpl_analyzer.format_export_file_data({
            "analyze_result": calculate_metrics,
            "filename_title": model_name,
        })
    except Exception:
        return "", []

    period_text = str(summary_df.iat[1, 1] or "").strip()
    rows = []
    for row_index in range(3, 23):
        category = str(summary_df.iat[row_index, 0] or "").strip()
        metric = str(summary_df.iat[row_index, 1] or "").strip()
        if not category and not metric:
            continue
        rows.append({
            "category": category,
            "metric": metric,
            "index_value": str(summary_df.iat[row_index, 2] or "").strip(),
            "model_value": str(summary_df.iat[row_index, 3] or "").strip(),
        })
    return period_text, rows


def _build_global_preview_payload(task_id):
    task = Task.query.get(task_id)
    if not task:
        return None

    task_config = task.to_dict().get("config") or {}
    task_results = (
        TaskResult.query
        .options(
            load_only(
                TaskResult.id,
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.parameters,
                TaskResult.result,
                TaskResult.success,
                TaskResult.error_message,
                TaskResult.timestamp,
            )
        )
        .filter_by(task_id=task_id)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .all()
    )

    groups = OrderedDict()
    success_count = 0
    failed_count = 0

    for task_result in task_results:
        parameters = json.loads(task_result.parameters) if task_result.parameters else {}
        year_key = str(parameters.get("year") or "未分组")
        model_name = _detect_model_name(task.name, parameters)
        group = groups.setdefault(year_key, {
            "group_key": year_key,
            "group_label": f"{year_key} 年",
            "year": year_key,
            "period": "",
            "columns": [],
            "rows": OrderedDict(),
            "failed_results": 0,
        })

        column_key = f"result_{task_result.id}"
        group["columns"].append({
            "column_key": column_key,
            "result_id": task_result.id,
            "step_index": task_result.step_index,
            "header": _build_parameter_header(parameters),
            "model_name": model_name,
            "success": bool(task_result.success),
            "timestamp": task_result.timestamp.isoformat() if task_result.timestamp else None,
            "parameter_values": parameters.get("parameter") if isinstance(parameters.get("parameter"), list) else [],
        })

        if not task_result.success:
            failed_count += 1
            group["failed_results"] += 1
            continue

        result_core = _extract_result_core(task_result)
        calculate_metrics = result_core.get("calculate_metrics") if isinstance(result_core, dict) else {}
        period_text, summary_rows = _extract_summary_rows(calculate_metrics, model_name)
        if not summary_rows:
            failed_count += 1
            group["failed_results"] += 1
            continue

        success_count += 1
        if period_text and not group["period"]:
            group["period"] = period_text

        for summary_row in summary_rows:
            row_key = f"{summary_row['category']}::{summary_row['metric']}"
            row = group["rows"].setdefault(row_key, {
                "category": summary_row["category"],
                "metric": summary_row["metric"],
                "index_value": summary_row["index_value"],
                "values": {},
            })
            if not row["index_value"] and summary_row["index_value"]:
                row["index_value"] = summary_row["index_value"]
            row["values"][column_key] = summary_row["model_value"]

    serialized_groups = []
    for year_key in sorted(groups.keys(), reverse=True):
        group = groups[year_key]
        ordered_rows = []
        for row in group["rows"].values():
            ordered_rows.append({
                "category": row["category"],
                "metric": row["metric"],
                "index_value": row["index_value"],
                "values": {
                    column["column_key"]: row["values"].get(column["column_key"], "")
                    for column in group["columns"]
                },
            })

        serialized_groups.append({
            "group_key": group["group_key"],
            "group_label": group["group_label"],
            "year": group["year"],
            "period": group["period"],
            "columns": group["columns"],
            "rows": ordered_rows,
            "failed_results": group["failed_results"],
            "column_count": len(group["columns"]),
        })

    return {
        "task": {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "stock_code": task_config.get("stock_code"),
            "market_type": task_config.get("market_type"),
        },
        "summary": {
            "total_results": len(task_results),
            "success_results": success_count,
            "failed_results": failed_count,
            "group_count": len(serialized_groups),
        },
        "groups": serialized_groups,
    }


def _sanitize_excel_sheet_name(name, fallback):
    raw_name = str(name or fallback or "Sheet")
    invalid_chars = set('\\/:*?[]')
    cleaned = ''.join('_' if char in invalid_chars else char for char in raw_name).strip()
    cleaned = cleaned[:31].strip() or fallback
    return cleaned


def _build_global_preview_workbook(payload):
    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)
    header_fill = PatternFill("solid", fgColor="F7E1A1")
    sub_header_fill = PatternFill("solid", fgColor="FCECC5")
    first_col_fill = PatternFill("solid", fgColor="F7E1A1")
    title_font = Font(name="Microsoft YaHei", size=12, bold=True)
    header_font = Font(name="Microsoft YaHei", size=11, bold=True)
    body_font = Font(name="Microsoft YaHei", size=10, bold=False)
    center_alignment = Alignment(horizontal="center", vertical="center")
    thin_side = Side(style="thin", color="D0D0D0")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    groups = payload.get("groups") or []
    if not groups:
        sheet = workbook.create_sheet("全局预览")
        sheet.append(["暂无可导出的分组数据"])
        return workbook

    used_sheet_names = set()
    for index, group in enumerate(groups, start=1):
        base_name = _sanitize_excel_sheet_name(group.get("group_label"), f"分组{index}")
        sheet_name = base_name
        suffix = 1
        while sheet_name in used_sheet_names:
            suffix += 1
            suffix_text = f"_{suffix}"
            sheet_name = f"{base_name[:31 - len(suffix_text)]}{suffix_text}"
        used_sheet_names.add(sheet_name)

        sheet = workbook.create_sheet(sheet_name)
        task = payload.get("task") or {}
        stock_code = task.get("stock_code") or group.get("year") or task.get("name") or ""
        columns = group.get("columns") or []
        row_1 = [stock_code, "", ""]
        for column in columns:
            row_1.append(column.get("header") or f"结果 {column.get('result_id')}")
        sheet.append(row_1)

        header = ["指标类型", "指标", "指数"]
        for column in columns:
            model_label = column.get("model_name") or "模型"
            if not column.get("success", True):
                model_label = f"{model_label}(失败)"
            header.append(model_label)
        sheet.append(header)

        for row in group.get("rows") or []:
            values = [
                row.get("category") or "",
                row.get("metric") or "",
                row.get("index_value") or "",
            ]
            for column in columns:
                values.append((row.get("values") or {}).get(column.get("column_key"), ""))
            sheet.append(values)

        if columns:
            sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
        sheet.freeze_panes = "A3"
        width_map = {
            "A": 14,
            "B": 22,
            "C": 14,
        }
        for column_index in range(4, len(header) + 1):
            width_map[get_column_letter(column_index)] = 18
        for key, width in width_map.items():
            sheet.column_dimensions[key].width = width

        sheet.row_dimensions[1].height = 26
        sheet.row_dimensions[2].height = 24

        max_row = sheet.max_row
        max_col = sheet.max_column
        for row_index in range(1, max_row + 1):
            for col_index in range(1, max_col + 1):
                cell = sheet.cell(row=row_index, column=col_index)
                cell.alignment = center_alignment
                cell.border = thin_border
                cell.font = body_font
                if row_index == 1:
                    cell.fill = header_fill
                    cell.font = title_font
                elif row_index == 2:
                    cell.fill = sub_header_fill
                    cell.font = header_font
                if col_index == 1 and row_index >= 2:
                    cell.fill = first_col_fill
                    if row_index == 2:
                        cell.font = header_font

        if group.get("period"):
            period_col = max_col + 1
            sheet.cell(row=1, column=period_col, value="区间")
            sheet.cell(row=2, column=period_col, value=group.get("period"))
            period_letter = get_column_letter(period_col)
            sheet.column_dimensions[period_letter].width = 24
            for row_index in (1, 2):
                cell = sheet.cell(row=row_index, column=period_col)
                cell.alignment = center_alignment
                cell.border = thin_border
                cell.font = title_font if row_index == 1 else body_font
                cell.fill = header_fill if row_index == 1 else sub_header_fill

    return workbook


@bp.route("/api/global-preview/<task_id>", methods=["GET"])
def get_global_preview(task_id):
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
def export_global_preview(task_id):
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
