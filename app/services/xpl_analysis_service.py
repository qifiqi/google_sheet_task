"""XPL 分析请求的应用服务（docs/design/api-model-query-audit/01 §5.8）。

承担参数解析、结果规整与成败判定；路由只做 HTTP 编排。
返回统一形态：{ok, message, data:{results, metrics}}。
"""

from __future__ import annotations

from typing import Any, Dict

from app.exceptions import ValidationError
from app.services.performance_analysis.request_dto import MetricsRuntimeParamsDTO
from app.services.xpl_service import xpl_analyzer

_EMPTY_RESULT_DATA: Dict[str, Any] = {"results": [], "metrics": {}}


def _parse_runtime_params(payload):
    """解析并校验 runtime_params（市场阶段阈值），非法输入抛 ValidationError。"""
    if payload is None:
        return MetricsRuntimeParamsDTO(), None
    if not isinstance(payload, dict):
        raise ValidationError("runtime_params 必须是对象")
    try:
        return MetricsRuntimeParamsDTO.from_raw(payload), None
    except ValueError as exc:
        raise ValidationError(str(exc))


def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """把 xpl_analyzer 的 {status, message, results, metrics} 规整为统一形态。"""
    ok = result.get("status") == "success"
    return {
        "ok": ok,
        "message": result.get("message", ""),
        "data": {
            "results": result.get("results", []),
            "metrics": result.get("metrics", {}),
        },
    }


class XplAnalysisService:
    """文本 / Google Sheet 两个分析入口的共享编排逻辑。"""

    def analyze_text(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_data = payload.get("data", "")
        time_format = payload.get("time_format", "auto")
        runtime_params, _ = _parse_runtime_params(payload.get("runtime_params"))

        result = xpl_analyzer.analyze(
            data=input_data,
            time_format=time_format,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)

    def analyze_sheet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        spreadsheet_id = payload.get("spreadsheet_id", "")
        google_sheet_url = payload.get("google_sheet_url", "")
        google_sheet_name = payload.get("google_sheet_name", "auto")
        runtime_params, _ = _parse_runtime_params(payload.get("runtime_params"))

        result = xpl_analyzer.analyze_v1(
            spreadsheet_id=spreadsheet_id,
            google_sheet_name=google_sheet_name,
            runtime_params=runtime_params,
        )
        return _normalize_result(result)


xpl_analysis_service = XplAnalysisService()
