"""回测域 API（自 backtest_training.py / backtest_multi_product.py 归位，URL 不变）。

- bt_api_bp（/backtest-training）与 bmp_api_bp（/backtest-multi-product）两个蓝图
  共存一文件：bt/bmp 的 API 端点同构，页面路由仍留在原页面蓝图；
- import-excel / calculate-ratios 挂保护性限流（06 §3，rate_limit_heavy）。
"""

from __future__ import annotations

import json

from flask import Blueprint, current_app, request

from app.exceptions import BadRequestError, NotFoundError, ValidationError
from app.extensions import limiter
from app.schemas.backtest import CalculateRatiosSchema, UpdateRatiosSchema
from app.services.backtest_excel_service import BacktestExcelService
from app.services.backtest_multi_product_preview import build_multi_product_global_preview_payload
from app.services.backtest_multi_product_service import (
    BACKTEST_MULTI_PRODUCT_TASK_TYPE,
    normalize_multi_product_config,
    update_task_ratios,
)
from app.services.backtest_report_query_service import (
    C3_PARAMETER_FIELDS,
    build_backtest_result_export_data,
    build_backtest_result_export_rows,
    build_c3_summary_rows,
    build_global_preview_payload,
    infer_backtest_model_version,
    load_backtest_task,
    load_backtest_task_result,
)
from app.services.performance_analysis.historical_metrics import extract_core_metrics
from app.services.task import task_manager
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.backtest_report_metadata import get_backtest_model_version, get_price_type
from app.utils.c7_result_normalizer import normalize_c7_result_metrics
from app.utils.request_parsing import parse_body
from app.utils.return_series import parse_return_series_fields
from app.utils.task_types import normalize_task_type


bt_api_bp = Blueprint("backtest_training_api", __name__, url_prefix="/backtest-training")
bmp_api_bp = Blueprint("backtest_multi_product_api", __name__, url_prefix="/backtest-multi-product")


def _rate_limit(config_key, default):
    """限流阈值经 config_manager 运行时可调（零重启）。"""
    from app.services.config_manager import get_config_manager

    return get_config_manager().get_config(config_key, default)


def _user_key():
    from flask import g

    return f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}"


def _sanitize_json_value(value):
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    return value


def _parse_json(raw, default):
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


# ==================== bt：Excel 导入 / 结果查询 ====================


@bt_api_bp.route("/api/import-excel", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_heavy', 6) or 6}/minute",
    key_func=_user_key,
)
def import_excel():
    excel_file = request.files.get("file")
    if not excel_file or not excel_file.filename:
        raise BadRequestError("请先上传 Excel 文件")

    data = BacktestExcelService().import_uploaded_excel(excel_file)
    return success(data=_sanitize_json_value(data))


@bt_api_bp.route("/api/task-results/<task_id>", methods=["GET"])
@login_required
def get_task_results_by_task_id(task_id):
    """Return paginated task result summaries for the detail page."""
    load_backtest_task(task_id)

    page = request.args.get("page", default=1, type=int) or 1
    per_page = request.args.get("per_page", default=10, type=int) or 10
    page = max(page, 1)
    per_page = max(min(per_page, 100), 1)

    page_data = task_manager.get_task_results_page_raw(task_id, page, per_page)
    results = [
        {
            **item,
            "parameters": json.loads(item["parameters"]) if item["parameters"] else {},
        }
        for item in page_data["items"]
    ]

    return success(data={
        "task_id": task_id,
        "items": results,
        "total": page_data["total"],
        "pages": page_data["pages"],
        "current_page": page_data["current_page"],
        "per_page": page_data["per_page"],
    })


@bt_api_bp.route("/api/task-result/<int:task_result_id>", methods=["GET"])
@login_required
def get_task_result_detail(task_result_id):
    """Return the full task result payload for the result page."""
    task_result, task = load_backtest_task_result(task_result_id)

    export_data = build_backtest_result_export_data(task_result, task)

    task_config = task.to_dict().get("config") or {}
    sheet = task_config.get("sheet") if isinstance(task_config.get("sheet"), dict) else {}
    return_series = (
        task_manager.get_return_entity(task_result.return_series_id)
        if task_result.return_series_id
        else None
    )
    return success(data={
        "result": _sanitize_json_value(export_data["analyze_result"]),
        "word_report_payload": {
            "report_type": "RPT-S",
            "task_id": task.id,
            "return_series_id": task_result.return_series_id,
            "products": [{
                "stock_code": return_series.stock_code,
                "product_name": return_series.stock_name,
            }] if return_series else [],
            "metadata": {
                "model_version": get_backtest_model_version(
                    sheet.get("title")
                    or task_config.get("title")
                    or task_config.get("spreadsheet_title")
                ),
                "price_type": get_price_type(task_config.get("price_mode") or task_config.get("price_type")),
            },
        } if task_result.return_series_id else None,
    })


@bt_api_bp.route("/api/task-result/<int:task_result_id>/export-preview", methods=["GET"])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_export', 10) or 10}/minute",
    key_func=_user_key,
)
def get_task_result_export_preview(task_result_id):
    task_result, task = load_backtest_task_result(task_result_id)

    try:
        export_data = build_backtest_result_export_data(task_result, task)
        rows = build_backtest_result_export_rows(export_data)
    except Exception:
        current_app.logger.exception("Failed to build backtest result export preview")
        raise BadRequestError("预览数据生成失败")

    return success(data={
        "filename": export_data["filename"],
        "rows": rows,
    })


@bt_api_bp.route("/api/task-summary/<task_id>", methods=["GET"])
@login_required
def get_task_summary(task_id):
    task = load_backtest_task(task_id)

    task_config = task.to_dict().get("config") or {}
    model_version = infer_backtest_model_version(task_config)
    if model_version != "c3":
        raise BadRequestError("当前汇总页仅支持 C3 回测任务")

    rows, parameter_group_count = build_c3_summary_rows(task_id)

    return success(data={
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


@bt_api_bp.route("/api/global-preview/<task_id>", methods=["GET"])
@login_required
def get_global_preview(task_id):
    load_backtest_task(task_id)

    payload = build_global_preview_payload(task_id)
    if payload is None:
        raise NotFoundError("任务不存在")

    return success(data=_sanitize_json_value(payload))


# ==================== bmp：批量导出构建块（P3 行为级合并的复用件，测试覆盖） ====================


def _build_excel_download_name(task_name, fallback_id: str) -> str:
    safe_name = "".join(char if char not in '\\/:*?"<>|' else "_" for char in str(task_name or "").strip())
    safe_name = safe_name.rstrip(" .")
    return f"{safe_name or fallback_id}.xlsx"


def _build_zip_member_name(task_name: str | None, fallback_id: str, used_names: set[str]) -> str:
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


# ==================== bmp：Excel 导入 / 结果查询 / 全局预览 ====================


def _infer_product_export_model_name(product):
    if not isinstance(product, dict):
        return "C3"

    sheet = product.get("sheet") or {}
    for source in (product.get("model_name"), sheet.get("title"), product.get("model_version")):
        title = str(source or "").upper()
        for model_name in ("C7", "C5", "C4", "C3"):
            if model_name in title:
                return model_name
    return "C3"


def _build_word_report_payload(task: dict, task_result) -> dict | None:
    """按当前结果的参数方案构造多品 Word 报告请求。"""
    try:
        config = normalize_multi_product_config(task.get("config") or {})
    except ValidationError:
        # 软失败：历史/残缺配置下 Word 报告段落返回 None，主流程继续
        return None
    selected_parameters = _parse_json(task_result.parameters, {})
    group_index = str(selected_parameters.get("parameter_group_index") or 0)
    return {
        "report_type": "RPT-M",
        "task_id": task["id"],
        "group_key": group_index,
        # normalize_multi_product_config 已把历史布尔配置归一为 weighting_mode。
        "weighting_mode": config.get("weighting_mode") or "daily_compound",
        "ratios": [
            {"product_index": product["product_index"], "ratio": product["ratio"]}
            for product in config["products"]
        ],
    }


@bmp_api_bp.route("/api/import-excel", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_heavy', 6) or 6}/minute",
    key_func=_user_key,
)
def bmp_import_excel():
    excel_file = request.files.get("file")
    if not excel_file or not excel_file.filename:
        raise BadRequestError("请先上传 Excel 文件")
    data = BacktestExcelService().import_uploaded_excel(excel_file)
    return success(data=_sanitize_json_value(data))


@bmp_api_bp.route("/api/task-results/<task_id>", methods=["GET"])
@login_required
def bmp_get_task_results_by_task_id(task_id):
    _load_multi_product_task_or_raise(task_id)

    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = max(min(request.args.get("per_page", default=10, type=int) or 10, 100), 1)
    page_data = task_manager.get_task_results_page_raw(task_id, page, per_page)
    results = [
        {**item, "parameters": _parse_json(item["parameters"], {})}
        for item in page_data["items"]
    ]
    return success(data={
        "task_id": task_id,
        "items": results,
        "total": page_data["total"],
        "pages": page_data["pages"],
        "current_page": page_data["current_page"],
        "per_page": page_data["per_page"],
    })


@bmp_api_bp.route("/api/task-result/<int:task_result_id>", methods=["GET"])
@login_required
def bmp_get_task_result_detail(task_result_id):
    task_result = task_manager.get_required_result_entity(task_result_id)
    task = _load_multi_product_task_or_raise(task_result.task_id)

    payload = _parse_json(task_result.result, {})
    if isinstance(payload, dict) and payload:
        prioritized_keys = ("metrics_payload", "calculate_metrics", "weighted_calculate_metrics", "analyze_result")
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
    calculate_metrics = extract_core_metrics(value)
    sheet_result = {
        key: item
        for key, item in value.items()
        if key not in {"metrics_payload", "calculate_metrics", "analyze_result"}
    } if isinstance(value, dict) else {}

    daily_returns = {}
    if task_result.return_series_id:
        return_series = task_manager.get_return_entity(task_result.return_series_id)
        if return_series:
            rows = parse_return_series_fields(return_series)
            daily_returns = {
                "dates": [row["date"] for row in rows],
                "index_returns": [row.get("index_return") for row in rows],
                "start_returns": [row.get("start_return") for row in rows],
            }

    task_config = _parse_json(task.get("config"), {})
    products = task_config.get("products") if isinstance(task_config, dict) else []
    parameters = _parse_json(task_result.parameters, {})
    product_index = parameters.get("product_index") if isinstance(parameters, dict) else None
    product = products[product_index] if isinstance(product_index, int) and 0 <= product_index < len(products) else {}
    model_name = _infer_product_export_model_name(product)
    if model_name == "C7":
        sheet_result = normalize_c7_result_metrics(sheet_result)

    return success(data={
        "result": _sanitize_json_value({
            **(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "sheet_result": sheet_result,
            "daily_returns": daily_returns,
            "model_name": model_name,
        }),
        "word_report_payload": _build_word_report_payload(task, task_result),
    })


@bmp_api_bp.route("/api/global-preview/<task_id>", methods=["GET"])
@login_required
def bmp_get_global_preview(task_id):
    _load_multi_product_task_or_raise(task_id)
    payload = build_multi_product_global_preview_payload(task_id)
    if payload is None:
        raise NotFoundError("任务不存在")
    return success(data=_sanitize_json_value(payload))


@bmp_api_bp.route("/api/global-preview/<task_id>/calculate-ratios", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_heavy', 6) or 6}/minute",
    key_func=_user_key,
)
def bmp_calculate_ratios(task_id):
    _load_multi_product_task_or_raise(task_id)
    data = parse_body(CalculateRatiosSchema)
    ratios = data.ratios
    payload = build_multi_product_global_preview_payload(task_id, ratios_override=ratios)
    if payload is None:
        raise NotFoundError("任务不存在")
    return success(data=_sanitize_json_value(payload))


@bmp_api_bp.route("/api/global-preview/<task_id>/ratios", methods=["PUT"])
@login_required
def bmp_update_ratios(task_id):
    task = _load_multi_product_task_or_raise(task_id)
    ratios = parse_body(UpdateRatiosSchema).ratios

    update_task_ratios(task_id, task.get("config") or {}, ratios)
    payload = build_multi_product_global_preview_payload(task_id)
    return success(
        data=_sanitize_json_value(payload or {}),
        message="比例已保存",
    )


def _load_multi_product_task_or_raise(task_id: str):
    """加载多品回测任务 dict；不存在抛 NotFoundError（404），类型不符抛 ValidationError。"""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")
    if normalize_task_type(task["task_type"]) != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        raise ValidationError("当前接口仅支持多品数据回测任务")
    return task
