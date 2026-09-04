from flask import Blueprint

from app.exceptions import BadRequestError
from app.utils.api_response import success
from app.utils.auth import login_required
from app.utils.db_monitor import DatabaseMonitor
from app.utils.logger import get_logger

logger = get_logger(__name__)

database_api_bp = Blueprint('database_api', __name__)

@database_api_bp.route('/database/status', methods=['GET'])
@login_required
def get_database_status():
    """获取数据库状态"""
    report = DatabaseMonitor.get_full_report()
    return success(data={"report": report})

@database_api_bp.route('/database/vacuum', methods=['POST'])
@login_required
def vacuum_database():
    """压缩数据库"""
    result = DatabaseMonitor.vacuum_database()
    if result.get('success'):
        return success(data={"result": result})
    raise BadRequestError(result.get('message', result.get('error')))

@database_api_bp.route('/database/suggestions', methods=['GET'])
@login_required
def get_optimization_suggestions():
    """获取数据库优化建议"""
    suggestions = DatabaseMonitor.suggest_optimizations()
    return success(data={"suggestions": suggestions})
