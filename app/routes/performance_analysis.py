import json
from itertools import chain

from flask import Blueprint, Response, stream_with_context, current_app

from app.routes.page_files import register_page_routes

from app.extensions import limiter, rate_limit_config, rate_limit_user_key
from app.schemas.performance_analysis import PerformanceAnalysisPayloadSchema, WeightCombinationSchema
from app.services.performance_analysis.service import performance_analysis_service
from app.utils.api_response import error, success
from app.utils.auth import login_required, page_login_required
from app.utils.request_parsing import parse_body


performance_analysis_bp = Blueprint("performance_analysis", __name__)

register_page_routes(
    performance_analysis_bp,
    [
        ("/", "performance_analysis/index.html"),
        ("/v2", "performance_analysis/v2.html"),
        ("/weight_combination", "performance_analysis/weight_combination.html"),
    ],
    guard=page_login_required,
)


def _run_analyze(analyze_fn):
    payload = parse_body(PerformanceAnalysisPayloadSchema).root
    result = analyze_fn(payload)
    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    return error(result["message"], http_status=400, data=result["data"])


@performance_analysis_bp.route("/analyze", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def analyze_data():
    return _run_analyze(performance_analysis_service.analyze_text)


@performance_analysis_bp.route("/v1/analyze", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def analyze_data_v1():
    return _run_analyze(performance_analysis_service.analyze_sheet)


@performance_analysis_bp.route("/v1/weight_combination", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def v1_weight_combination():
    """权重组合分析接口，返回流式 NDJSON（换行分隔的 JSON）。

    每个组合结果作为一行 JSON 对象返回，前端可以流式处理和渐进式渲染。
    """

    payload = parse_body(WeightCombinationSchema).model_dump()

    def generate():
        """生成器函数，逐个产出组合结果的 JSON 行。"""
        with current_app.app_context():
            try:
                for combination in performance_analysis_service.weight_combination(payload):
                    # 每个组合输出为一行 JSON
                    yield json.dumps(combination, ensure_ascii=False) + '\n'
            except Exception as e:
                # 错误也以 JSON 格式返回
                error_obj = {
                    'error': True,
                    'message': str(e)
                }
                yield json.dumps(error_obj, ensure_ascii=False) + '\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # 禁用 nginx 缓冲，确保流式传输
        }
    )



