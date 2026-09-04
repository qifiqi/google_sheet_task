from flask import Blueprint, render_template, request

from app.exceptions import ValidationError
from app.services.xpl_analysis_service import _EMPTY_RESULT_DATA, xpl_analysis_service
from app.utils.api_response import error, success
from app.utils.logger import get_logger

logger = get_logger(__name__)

xpl_bp = Blueprint('xpl', __name__)


@xpl_bp.route('/')
def index():
    """Excel数据分析工具首页"""
    return render_template('xpl/index.html')


@xpl_bp.route('/v1', methods=['GET'])
def index_v1():
    """V1：Google Sheet 分析页面"""
    return render_template('xpl/v1.html')


@xpl_bp.route('/v2', methods=['GET'])
def index_v2():
    """V2：支持多数据源的回测分析页面。"""
    return render_template('xpl/v2.html')


@xpl_bp.route('/analyze', methods=['POST'])
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

    try:
        result = xpl_analysis_service.analyze_text(payload)
    except ValidationError as exc:
        return error(str(exc), http_status=400, data=_EMPTY_RESULT_DATA)
    except Exception as exc:
        logger.exception("处理分析请求时出错")
        return error('处理请求时出错', http_status=500, data=_EMPTY_RESULT_DATA)

    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    # 分析器报告的数据级失败保持原有 200 语义（前端按 status/code 判定展示）。
    return error(result["message"], http_status=200, data=result["data"])


@xpl_bp.route('/v1/analyze', methods=['POST'])
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

    try:
        result = xpl_analysis_service.analyze_sheet(payload)
    except ValidationError as exc:
        return error(str(exc), http_status=400, data=_EMPTY_RESULT_DATA)
    except Exception as exc:
        logger.exception("处理分析请求时出错")
        return error('处理请求时出错', http_status=500, data=_EMPTY_RESULT_DATA)

    if result["ok"]:
        return success(data=result["data"], message=result["message"])
    # 分析器报告的数据级失败保持原有 200 语义（前端按 status/code 判定展示）。
    return error(result["message"], http_status=200, data=result["data"])
