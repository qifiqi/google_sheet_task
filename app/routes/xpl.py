from flask import Blueprint, g, render_template, request

from app.extensions import limiter
from app.services.xpl_analysis_service import _EMPTY_RESULT_DATA, xpl_analysis_service
from app.utils.api_response import error, success
from app.utils.logger import get_logger
from app.utils.auth import login_required, page_login_required

logger = get_logger(__name__)

xpl_bp = Blueprint('xpl', __name__)


def _rate_limit(config_key, default):
    """限流阈值经 config_manager 运行时可调（零重启）。"""
    from app.services.config_manager import get_config_manager

    return get_config_manager().get_config(config_key, default)


def _user_key():
    return f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}"


@xpl_bp.route('/')
@page_login_required
def index():
    """Excel数据分析工具首页"""
    return render_template('xpl/index.html')


@xpl_bp.route('/v1', methods=['GET'])
@page_login_required
def index_v1():
    """V1：Google Sheet 分析页面"""
    return render_template('xpl/v1.html')


@xpl_bp.route('/v2', methods=['GET'])
@page_login_required
def index_v2():
    """V2：支持多数据源的回测分析页面。"""
    return render_template('xpl/v2.html')


@xpl_bp.route('/analyze', methods=['POST'])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_analyze', 10) or 10}/minute",
    key_func=_user_key,
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
    payload = request.get_json(silent=True)
    if not payload:
        return error('请求体不能为空', http_status=400, data=_EMPTY_RESULT_DATA)

    # 不在路由内 try/except：ValidationError → 全局 400，其余异常 → 全局 500。
    result = xpl_analysis_service.analyze_text(payload)

    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    # 数据级失败（输入数据不满足分析前提）按 400 下发；前端按信封 message 展示。
    return error(result["message"], http_status=400, data=result["data"])


@xpl_bp.route('/v1/analyze', methods=['POST'])
@login_required
@limiter.limit(
    lambda: f"{_rate_limit('rate_limit_analyze', 10) or 10}/minute",
    key_func=_user_key,
)
def analyze_data_v1():
    """
    API接口：分析 Google Sheet 数据

    请求体 (JSON):
    {
        "spreadsheet_id": "",
        "google_sheet_url": "",
        "google_sheet_name": ""
    }

    返回 (JSON, 统一信封):
    data = {"results": [...], "metrics": {...}}
    """
    payload = request.get_json(silent=True)
    if not payload:
        return error('请求体不能为空', http_status=400, data=_EMPTY_RESULT_DATA)

    # 不在路由内 try/except：ValidationError → 全局 400，其余异常 → 全局 500。
    result = xpl_analysis_service.analyze_sheet(payload)

    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    # 数据级失败（输入数据不满足分析前提）按 400 下发；前端按信封 message 展示。
    return error(result["message"], http_status=400, data=result["data"])
