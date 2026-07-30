"""Normalized, list-safe presentations for C-series task result records."""

from __future__ import annotations

import json
from typing import Any


CORE_METRIC_LABELS = {
    "return": "Return%",
    "annualized": "Annualized",
    "max_drawdown": "Max DD%",
    "index_return": "Index Return",
    "index_annualized": "指数 Annualized",
    "index_max_drawdown": "Index max dd",
    "fee_total": "Fee total",
    "fee_annualized": "Fee annualized",
    "turnover_rate": "年换手率",
    "return_beats": "return beats",
    "dd_beats": "ddBeats",
    "max_one_year_beats": "max(1y beats%)",
    "min_one_year_beats": "min(1y beats%)",
    "max_theoretical_leverage": "最大理论杠杆率",
    "avg_theoretical_leverage": "平均理论杠杆率",
    "unit_theoretical_leverage_return": "单位理论杠杆率收益",
    "max_actual_leverage": "最大实际杠杆率",
    "avg_actual_leverage": "平均实际杠杆率",
    "unit_actual_leverage_return": "单位实际杠杆率收益",
    "index_sharpe": "i xpl",
    "model_sharpe": "s xpl",
}

CORE_METRIC_KEYS = tuple(CORE_METRIC_LABELS)

C3_METRIC_CELLS = {
    "return": "I15",
    "annualized": "I16",
    "max_drawdown": "I17",
    "index_return": "I18",
    "index_annualized": "I19",
    "index_max_drawdown": "I20",
    "fee_total": "I21",
    "fee_annualized": "I22",
    "turnover_rate": "I23",
}

C4_C5_METRIC_CELLS = {
    "return": "D2",
    "annualized": "D3",
    "max_drawdown": "D4",
    "index_return": "D5",
    "index_annualized": "D6",
    "index_max_drawdown": "D7",
    "fee_total": "D8",
    "fee_annualized": "D9",
    "turnover_rate": "D10",
    "return_beats": "D11",
    "dd_beats": "D12",
    "max_one_year_beats": "D13",
    "min_one_year_beats": "D14",
    "max_theoretical_leverage": "D15",
    "avg_theoretical_leverage": "D16",
    "unit_theoretical_leverage_return": "D17",
    "max_actual_leverage": "D18",
    "avg_actual_leverage": "D19",
    "unit_actual_leverage_return": "D20",
}

C7_METRIC_CELLS = {
    "return": "D8",
    "annualized": "D9",
    "max_drawdown": "D10",
    "index_return": "D11",
    "index_annualized": "D12",
    "index_max_drawdown": "D13",
    "fee_total": "D14",
    "fee_annualized": "D15",
    "turnover_rate": "D16",
    "return_beats": "D17",
    "dd_beats": "D18",
    "max_one_year_beats": "D19",
    "min_one_year_beats": "D20",
    "max_theoretical_leverage": "D21",
    "avg_theoretical_leverage": "D22",
    "unit_theoretical_leverage_return": "D23",
    "max_actual_leverage": "D24",
    "avg_actual_leverage": "D25",
    "unit_actual_leverage_return": "D26",
}

ANALYSIS_METRIC_LABELS = {
    "start_annualized_return": "模型年化收益",
    "index_annualized_return": "指数年化收益",
    "annualized_return_diff": "年化超额收益",
    "outperform_year": "跑赢年份占比",
    "monthly_excess_return_percentage_last_return": "月超额收益胜率",
    "avg_monthly_excess_returns": "平均月超额",
    "monthly_excess_volatility": "月超额波动率",
    "max_drawdown": "年最大超额回撤",
    "start_drawdown": "年最大回撤",
    "index_sharpe_ratio": "指数夏普比率",
    "start_sharpe_ratio": "模型夏普比率",
    "index_kama_ratio": "指数卡玛比率",
    "start_kama_ratio": "模型卡玛比率",
    "index_sotino_ratio": "指数所提诺比率",
    "start_sotino_ratio": "模型所提诺比率",
}


def _load_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _as_object(value: Any) -> dict[str, Any]:
    parsed = _load_json(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _task_kind(task_type: str | None) -> str:
    normalized = str(task_type or "").lower()
    if normalized == "google_sheet":
        return "c3"
    if normalized in {"google_sheet_c4", "google_sheet_c5"}:
        return "c4_c5"
    if normalized == "google_sheet_c7":
        return "c7"
    return "generic"


def _empty_metrics() -> dict[str, Any]:
    return {key: None for key in CORE_METRIC_KEYS}


def _metrics_from_cells(
    raw_metrics: dict[str, Any],
    cells: dict[str, str],
    flat_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = _empty_metrics()
    metrics.update({key: raw_metrics.get(cell) for key, cell in cells.items()})
    if flat_result is None:
        flat_result = raw_metrics.get("flat_result")
    if isinstance(flat_result, dict):
        metrics["index_sharpe"] = flat_result.get("index_sharpe_ratio")
        metrics["model_sharpe"] = flat_result.get("start_sharpe_ratio")
    return metrics


def _kline_date_range(kline: Any) -> str | None:
    if not isinstance(kline, list) or not kline:
        return None

    def date_of(item: Any) -> Any:
        if isinstance(item, dict):
            return item.get("stock_date") or item.get("date")
        if isinstance(item, (list, tuple)) and item:
            return item[0]
        return None

    start_date = date_of(kline[0])
    end_date = date_of(kline[-1])
    if not start_date or not end_date:
        return None
    return f"{start_date} 至 {end_date}"


def _parameter_context(parameters: Any, task_config: dict[str, Any]) -> dict[str, Any]:
    if isinstance(parameters, dict):
        parameter_source = parameters.get("parameter")
        if isinstance(parameter_source, list):
            values = parameter_source
        elif parameter_source not in (None, ""):
            values = [parameter_source]
        else:
            ignored_keys = {"kline", "stock_code", "stock_name", "year", "Kline_key"}
            values = [value for key, value in parameters.items() if key not in ignored_keys and isinstance(value, (str, int, float, bool))]
        stock_code = parameters.get("stock_code") or task_config.get("stock_code")
        stock_name = parameters.get("stock_name") or task_config.get("stock_name")
        period = parameters.get("year") or parameters.get("Kline_key") or task_config.get("year_n")
        kline = parameters.get("kline")
    elif isinstance(parameters, list):
        values = parameters[:-1] if parameters and isinstance(parameters[-1], list) else parameters
        stock_code = task_config.get("stock_code")
        stock_name = task_config.get("stock_name")
        period = task_config.get("year_n")
        kline = parameters[-1] if parameters and isinstance(parameters[-1], list) else None
    else:
        values = []
        stock_code = task_config.get("stock_code")
        stock_name = task_config.get("stock_name")
        period = task_config.get("year_n")
        kline = None

    string_values = [str(value) for value in values]
    return {
        "stock_code": str(stock_code) if stock_code not in (None, "") else None,
        "stock_name": str(stock_name) if stock_name not in (None, "") else None,
        "period": str(period) if period not in (None, "") else None,
        "kline_date_range": _kline_date_range(kline),
        "parameter_values": string_values[:8],
        "parameter_items": [
            {"label": f"参数 {index + 1}", "value": value}
            for index, value in enumerate(string_values[:8])
        ],
    }


def _model_name(model_key: str) -> tuple[str, str]:
    code, separator, name = model_key.partition("__")
    return code, name if separator and name else code


def _normalized_models(payload: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    if kind == "c3":
        return [{
            "key": "default",
            "code": "C3",
            "name": "C3",
            "analysis_status": payload.get("analysis_status"),
            "raw": payload,
            "metrics": _metrics_from_cells(payload, C3_METRIC_CELLS),
            "cells": C3_METRIC_CELLS,
        }]

    if kind == "c4_c5":
        cells = C4_C5_METRIC_CELLS
    elif kind == "c7":
        cells = C7_METRIC_CELLS
    else:
        cells = {}

    models = []
    for key, value in payload.items():
        if not isinstance(value, dict) or key in {"flat_result", "analyze_result"}:
            continue
        if kind == "c4_c5" and isinstance(value.get("D2:D20"), dict):
            metrics = _metrics_from_cells(value["D2:D20"], cells, value.get("flat_result"))
        elif kind == "generic":
            metrics = _metrics_from_cells(value, C4_C5_METRIC_CELLS)
        else:
            metrics = _metrics_from_cells(value, cells)
        code, name = _model_name(str(key))
        models.append({
            "key": str(key),
            "code": code,
            "name": name,
            "analysis_status": value.get("analysis_status"),
            "raw": value,
            "metrics": metrics,
            "cells": cells,
        })
    return models


def _public_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": model["key"],
        "code": model["code"],
        "name": model["name"],
        "analysis_status": model["analysis_status"],
        "metrics": model["metrics"],
    }


def _item(label: str, value: Any) -> dict[str, str]:
    if value in (None, ""):
        display_value = "-"
    elif isinstance(value, float):
        display_value = f"{value:.4f}"
    else:
        display_value = str(value)
    return {"label": label, "value": display_value}


def _detail_sections(model: dict[str, Any]) -> list[dict[str, Any]]:
    raw = model["raw"]
    cells = model["cells"]
    metric_items = [
        _item(CORE_METRIC_LABELS[key], model["metrics"].get(key))
        for key in CORE_METRIC_KEYS
        if model["metrics"].get(key) not in (None, "")
    ]
    sections = []
    if metric_items:
        sections.append({"key": "core", "title": "核心回测指标", "items": metric_items})

    cell_keys = set(cells.values())
    execution_items = [
        _item(key, value)
        for key, value in raw.items()
        if key not in cell_keys
        and key not in {"flat_result", "analyze_result", "analysis_status", "result_parameters"}
        and not isinstance(value, (dict, list))
    ]
    if execution_items:
        sections.append({"key": "execution", "title": "执行单元格结果", "items": execution_items})

    flat_result = raw.get("flat_result")
    if not isinstance(flat_result, dict) and model["key"] == "default":
        flat_result = raw.get("flat_result")
    analysis_items = [
        _item(label, flat_result.get(key))
        for key, label in ANALYSIS_METRIC_LABELS.items()
        if isinstance(flat_result, dict) and flat_result.get(key) not in (None, "")
    ]
    if analysis_items:
        sections.append({"key": "analysis", "title": "回测分析摘要", "items": analysis_items})
    return sections


def build_task_result_detail_presentation(
    result: Any,
    task_type: str | None,
    task_config: Any = None,
) -> dict[str, Any]:
    """Build the bounded, user-facing detail sections without exposing large raw payloads."""
    kind = _task_kind(task_type)
    payload = _as_object(getattr(result, "result", None))
    models = _normalized_models(payload, kind)
    return {
        "kind": kind,
        "models": [
            {"key": model["key"], "name": model["name"], "sections": _detail_sections(model)}
            for model in models
        ],
    }


def build_task_result_list_item(
    result: Any,
    task_name: str | None,
    task_type: str | None,
    task_config: Any = None,
) -> dict[str, Any]:
    """Return one compact, normalized result record for every C-series task type."""
    kind = _task_kind(task_type)
    parameters = _load_json(getattr(result, "parameters", None), {})
    task_config_object = _as_object(task_config)
    payload = _as_object(getattr(result, "result", None))
    models = _normalized_models(payload, kind)
    context = _parameter_context(parameters, task_config_object)
    public_models = [_public_model(model) for model in models]
    first_metrics = public_models[0]["metrics"] if public_models else _empty_metrics()

    return {
        "id": result.id,
        "task_id": result.task_id,
        "task_name": task_name or "未命名任务",
        "task_type": task_type,
        "step_index": result.step_index,
        "success": result.success,
        "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        "summary": {
            **context,
            "model_count": len(public_models),
            "model_names": [model["key"] for model in public_models],
            "analysis_status": payload.get("analysis_status"),
            "models": public_models,
            "metrics": first_metrics,
        },
    }
