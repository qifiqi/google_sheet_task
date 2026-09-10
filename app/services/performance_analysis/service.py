"""绩效分析 分析请求的应用服务（docs/design/api-model-query-audit/01 §5.8）。

承担参数解析、结果规整与成败判定；路由只做 HTTP 编排。
返回统一形态：{ok, message, data:{results, metrics}}。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.exceptions import ValidationError
from app.repositories import task_repository, task_result_repository
from app.services.performance_analysis.facade import calculate_v1_metrics
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.performance_analysis.portfolio_combiner import combine_product_returns
from app.utils.formatting import parse_lenient_json
from app.utils.return_series import extract_return_rows, parse_return_series_fields

_EMPTY_RESULT_DATA: Dict[str, Any] = {"results": [], "metrics": {}}

# 公开出口（routes 只允许引用公开符号；2026-09 审计 B3）
EMPTY_RESULT_DATA = _EMPTY_RESULT_DATA


def _parse_runtime_params(payload):
    """解析并校验 runtime_params（市场阶段阈值），非法输入抛 ValidationError。"""
    if payload is None:
        return MetricsRuntimeParamsDTO()
    if not isinstance(payload, dict):
        raise ValidationError("runtime_params 必须是对象")
    try:
        return MetricsRuntimeParamsDTO.from_raw(payload)
    except ValueError as exc:
        raise ValidationError(str(exc))


def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """把绩效分析器的 {status, message, results, metrics} 规整为统一形态。"""
    ok = result.get("status") == "success"
    return {
        "ok": ok,
        "message": result.get("message", ""),
        "data": {
            "results": result.get("results", []),
            "metrics": result.get("metrics", {}),
        },
    }


def get_index_annualized_rates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """提取组合的指数年化收益率。"""
    value = metrics.get("index_annualized_rates")
    return value if isinstance(value, list) else []


def get_start_max_drawdown(metrics: dict[str, Any]) -> Any:
    """提取组合策略的总最大回撤。"""
    drawdown = metrics.get("start_maximum_drawdown")
    if not isinstance(drawdown, dict):
        return None
    total = drawdown.get("total_maximum_drawdown")
    return total.get("drawdown") if isinstance(total, dict) else None


def _year_max_drawdown(metrics: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = metrics.get(key)
    return value.get("year_maximum_drawdown", []) if isinstance(value, dict) else []


def _weight_combinations(product_count: int, units: int):
    if product_count == 1:
        yield (units,)
        return
    for weight in range(units + 1):
        for remaining in _weight_combinations(product_count - 1, units - weight):
            yield (weight, *remaining)


def _product_data(task_result: Any) -> dict[str, Any]:
    parameters = parse_lenient_json(getattr(task_result, "parameters", None), {})
    parameters = parameters if isinstance(parameters, dict) else {}
    stock_code = parameters.get("stock_code")
    stock_name = parameters.get("stock_name") or parameters.get("product_name")
    rows = []
    if task_result.return_series_id:
        series = task_result_repository.get_return_entity(task_result.return_series_id)
        if series:
            rows = parse_return_series_fields(series)
            stock_code = series.stock_code or stock_code
            stock_name = series.stock_name or stock_name
    if not rows:
        rows = extract_return_rows(parse_lenient_json(task_result.result, {}))
    return {
        "result_id": task_result.id,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "returns": rows,
    }


class PerformanceAnalysisService:
    """文本 / Google Sheet 两个分析入口的共享编排逻辑。"""

    def analyze_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_data = payload.get("data", "")
        time_format = payload.get("time_format", "auto")
        runtime_params = _parse_runtime_params(payload.get("runtime_params"))

        result = performance_analyzer.analyze(
            data=input_data,
            time_format=time_format,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    def analyze_sheet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        spreadsheet_id = payload.get("spreadsheet_id", "")
        google_sheet_url = payload.get("google_sheet_url", "")
        google_sheet_name = payload.get("google_sheet_name", "auto")
        runtime_params = _parse_runtime_params(payload.get("runtime_params"))

        result = performance_analyzer.analyze_v1(
            spreadsheet_id=spreadsheet_id,
            google_sheet_name=google_sheet_name,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    async def weight_combination(self, payload: Dict[str, Any]):
        """按固定步长异步产出任务结果的全量权重组合。"""
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise ValidationError("task_id 不能为空")
        step = payload.get("step", 10)
        if not isinstance(step, int) or isinstance(step, bool) or step <= 0 or 100 % step:
            raise ValidationError("step 必须是能整除 100 的正整数")

        task_repository.get_required(task_id)
        products = []
        for result in task_result_repository.list_preview_entities(task_id, success_only=True):
            product = _product_data(result)
            if product["returns"]:
                products.append(product)
        if not products:
            raise ValidationError("任务没有可用于组合的成功收益序列")

        for units in _weight_combinations(len(products), 100 // step):
            weights = [unit * step for unit in units]
            active_products = [
                product for product, weight in zip(products, weights) if weight
            ]
            active_weights = [weight for weight in weights if weight]
            returns = combine_product_returns(active_products, weights=active_weights)
            if len(returns) < 2:
                continue
            metrics = calculate_v1_metrics(returns).metrics
            yield {
                "_weight_combination_v1": {
                    "annualized_rates": {
                        "index": get_index_annualized_rates(metrics),
                        "start": metrics.get("start_annualized_rates", []),
                    },
                    "year_max_drawdown": {
                        "index": _year_max_drawdown(metrics, "index_maximum_drawdown"),
                        "start": _year_max_drawdown(metrics, "start_maximum_drawdown"),
                    },
                    "stocks": [
                        {
                            "result_id": product["result_id"],
                            "stock_code": product["stock_code"],
                            "stock_name": product["stock_name"],
                            "ratio": weight,
                        }
                        for product, weight in zip(products, weights)
                    ],
                },
            }
            await asyncio.sleep(0)


performance_analysis_service = PerformanceAnalysisService()
