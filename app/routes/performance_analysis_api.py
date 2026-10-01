"""绩效分析 API（统一分析入口 analyze 与权重组合 weight-combination；页面路由已归位
app/routes/pages/performance_analysis.py，页面 URL 前缀 /performance-analysis）。"""

import json

from flask import Blueprint, Response, current_app, stream_with_context

from app.exceptions import AppException
from app.extensions import limiter, rate_limit_config, rate_limit_user_key
from app.schemas.performance_analysis import (
    PerformanceAnalysisPayloadSchema,
    WeightCombinationProductsQuerySchema,
    WeightCombinationSchema,
)
from app.services.performance_analysis.service import performance_analysis_service
from app.utils.api_response import error, success
from app.utils.auth import login_required
from app.utils.logger import get_logger
from app.utils.request_parsing import parse_body, parse_query


logger = get_logger(__name__)

performance_analysis_bp = Blueprint("performance_analysis", __name__)


@performance_analysis_bp.route("/analyze", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def analyze_data():
    """统一分析入口：载荷按数据来源分流（result_id / spreadsheet_id / data）。"""
    payload = parse_body(PerformanceAnalysisPayloadSchema).root
    result = performance_analysis_service.analyze(payload)
    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    return error(result["message"], http_status=400, data=result["data"])


@performance_analysis_bp.route("/weight-combination/products", methods=["GET"])
@login_required
def weight_combination_products():
    """权重组合分析：列出任务下可参与组合的产品及其已配置比例。

    供页面"产品选择 + 单股范围"面板使用；返回顺序与 weight_combination
    的产品装载顺序一致，前端按 result_id 回传勾选与范围。
    """
    query = parse_query(WeightCombinationProductsQuerySchema)
    data = performance_analysis_service.list_weight_combination_products(query.task_id.strip())
    return success(data=data)


@performance_analysis_bp.route("/weight-combination", methods=["POST"])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def weight_combination():
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
            except AppException as exc:
                # 业务异常文案本身面向用户（与 errors.py 信封同源），随流末行下发。
                yield json.dumps({'error': True, 'message': exc.message}, ensure_ascii=False) + '\n'
            except Exception:
                # 非业务异常细节只进日志，绝不下发 str(e)（errors.py 红线）。
                logger.exception("权重组合分析流式生成失败")
                yield json.dumps(
                    {'error': True, 'message': '权重组合分析处理失败，请稍后重试'},
                    ensure_ascii=False,
                ) + '\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # 禁用 nginx 缓冲，确保流式传输
        }
    )
