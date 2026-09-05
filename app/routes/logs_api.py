"""系统日志 API（自 config_api.py 归位，URL 不变）。

日志文件读取/解析已下沉 log_query_service（B3 收敛），路由只做参数编排。
"""

from flask import Blueprint, request

from app.services.log_query_service import query_latest_logs, query_system_logs
from app.utils.api_response import success
from app.utils.auth import login_required

logs_api_bp = Blueprint('logs_api', __name__)


@logs_api_bp.route('/logs', methods=['GET'])
@login_required
def get_logs():
    """获取系统日志"""
    logs = query_system_logs(
        limit=request.args.get('limit', 100, type=int),
        level_filter=request.args.get('level', ''),
        search=request.args.get('search', ''),
        date_filter=request.args.get('date', ''),
        task_id_filter=request.args.get('task_id', ''),
    )
    return success(data={"logs": logs})


@logs_api_bp.route('/logs/latest', methods=['GET'])
@login_required
def get_latest_logs():
    """获取最新的日志"""
    logs = query_latest_logs(
        since=request.args.get('since', ''),
        limit=request.args.get('limit', 50, type=int),
    )
    return success(data={"logs": logs})
