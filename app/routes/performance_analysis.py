from flask import Blueprint

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
def weight_combination():
    payload = parse_body(WeightCombinationSchema).root
    return performance_analysis_service.weight_combination(payload)


