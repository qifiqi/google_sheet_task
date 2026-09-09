from flask import Blueprint, request

from app.routes.page_files import register_page_routes, send_page

from app.extensions import limiter, rate_limit_config, rate_limit_user_key
from app.schemas.xpl import AnalyzePayloadSchema
from app.services.xpl_analysis_service import xpl_analysis_service
from app.utils.api_response import error, success
from app.utils.logger import get_logger
from app.utils.auth import login_required, page_login_required
from app.utils.request_parsing import parse_body

logger = get_logger(__name__)

xpl_bp = Blueprint('xpl', __name__)


# 页面路由表驱动化（ponytail 审计 D1）；/xpl/v1 页面已删除（审计 A2），分析 API 保留
register_page_routes(
    xpl_bp,
    [
        ('/', 'xpl/index.html'),
        ('/v2', 'xpl/v2.html'),
    ],
    guard=page_login_required,
)


def _run_analyze(analyze_fn):
    """analyze 端点共享体：parse → service → ok?success:error（审计 D6）。

    数据级失败（输入数据不满足分析前提）按 400 下发；前端按信封 message 展示。
    路由内不 try/except：ValidationError → 全局 400，其余异常 → 全局 500。
    """
    payload = parse_body(AnalyzePayloadSchema).root
    result = analyze_fn(payload)
    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    return error(result["message"], http_status=400, data=result["data"])


@xpl_bp.route('/analyze', methods=['POST'])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def analyze_data():
    """
    API接口：分析Excel数据

    请求体 (JSON):
    {
        "data": "2023-01-01 0.01\\n2023-01-02 0.02\\n...",
        "time_format": "YYYY-MM-DD"
    }

    返回 (JSON, 统一信封):
    data = {"results": [...], "metrics": {...}}
    """
    return _run_analyze(xpl_analysis_service.analyze_text)


@xpl_bp.route('/v1/analyze', methods=['POST'])
@login_required
@limiter.limit(
    lambda: f"{rate_limit_config('rate_limit_analyze', 10) or 10}/minute",
    key_func=rate_limit_user_key,
)
def analyze_data_v1():
    """
    API接口：分析 Google Sheet 数据（历史命名；xpl/v2 页面在用）

    请求体 (JSON):
    {
        "spreadsheet_id": "",
        "google_sheet_url": "",
        "google_sheet_name": ""
    }

    返回 (JSON, 统一信封):
    data = {"results": [...], "metrics": {...}}
    """
    return _run_analyze(xpl_analysis_service.analyze_sheet)
