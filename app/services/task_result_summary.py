"""Compact, list-safe summaries for task result records."""

import json


def _load_json_object(raw_value):
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _parameter_values(parameters):
    values = parameters.get("parameter")
    if isinstance(values, list):
        return [str(value) for value in values[:4]]
    if values not in (None, ""):
        return [str(values)]

    ignored_keys = {"kline", "stock_code", "year", "Kline_key"}
    return [
        f"{key}: {value}"
        for key, value in parameters.items()
        if key not in ignored_keys and isinstance(value, (str, int, float, bool))
    ][:4]


def _parameter_items(parameters):
    values = parameters.get("parameter")
    if isinstance(values, list):
        return [
            {"label": f"参数 {index + 1}", "value": str(value)}
            for index, value in enumerate(values[:4])
        ]

    ignored_keys = {"kline", "stock_code", "stock_name", "year", "Kline_key"}
    return [
        {"label": str(key), "value": str(value)}
        for key, value in parameters.items()
        if key not in ignored_keys and isinstance(value, (str, int, float, bool))
    ][:4]


def _kline_date_range(parameters):
    kline = parameters.get("kline")
    if not isinstance(kline, list) or not kline:
        return None

    def date_of(item):
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


def _result_metadata(result_payload):
    model_values = [value for value in result_payload.values() if isinstance(value, dict)]
    analysis_status = next(
        (
            value.get("analysis_status")
            for value in model_values
            if value.get("analysis_status")
        ),
        None,
    )
    return len(model_values), analysis_status, [str(key) for key, value in result_payload.items() if isinstance(value, dict)][:2]


def _metric_summary(model):
    """Extract the small set of backtest metrics needed by C-series lists."""
    sheet_metrics = model.get("D2:D20") if isinstance(model.get("D2:D20"), dict) else {}
    flat_metrics = model.get("flat_result") if isinstance(model.get("flat_result"), dict) else {}
    return {
        "return": sheet_metrics.get("D2", model.get("D2")),
        "annualized": sheet_metrics.get("D3", model.get("D3")),
        "max_drawdown": sheet_metrics.get("D4", model.get("D4")),
        "index_return": sheet_metrics.get("D5", model.get("D5")),
        "index_annualized": sheet_metrics.get("D6", model.get("D6")),
        "index_max_drawdown": sheet_metrics.get("D7", model.get("D7")),
        "index_sharpe": flat_metrics.get("index_sharpe_ratio"),
        "model_sharpe": flat_metrics.get("start_sharpe_ratio"),
    }


def _model_summaries(result_payload):
    summaries = []
    for key, value in result_payload.items():
        if not isinstance(value, dict):
            continue
        code, _, name = str(key).partition("__")
        summaries.append({
            "key": str(key),
            "code": code,
            "name": name or code,
            "analysis_status": value.get("analysis_status"),
            "metrics": _metric_summary(value),
        })
    return summaries


def build_task_result_list_item(result, task_name, task_type):
    """Return a result list record without exposing raw K-line or model JSON."""
    parameters = _load_json_object(result.parameters)
    result_payload = _load_json_object(result.result)
    model_count, analysis_status, model_names = _result_metadata(result_payload)
    models = _model_summaries(result_payload)

    return {
        "id": result.id,
        "task_id": result.task_id,
        "task_name": task_name or "未命名任务",
        "task_type": task_type,
        "step_index": result.step_index,
        "success": result.success,
        "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        "summary": {
            "stock_code": parameters.get("stock_code"),
            "stock_name": parameters.get("stock_name"),
            "period": parameters.get("year") or parameters.get("Kline_key"),
            "kline_date_range": _kline_date_range(parameters),
            "parameter_values": _parameter_values(parameters),
            "parameter_items": _parameter_items(parameters),
            "model_count": model_count,
            "model_names": model_names,
            "analysis_status": analysis_status,
            "models": models,
            "metrics": models[0]["metrics"] if models else _metric_summary({}),
        },
    }
