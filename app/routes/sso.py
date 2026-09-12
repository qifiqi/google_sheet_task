"""主服务 SSO 换票接口（docs/design/sso-integration-2026-09/）。

POST /api/auth/sso/exchange：header Token 携带主服务令牌，免登换发本地
access/refresh JWT（返回结构与 /api/auth/login 一致，前端复用 setTokens
管线）。令牌只走 header，不进 body/查询串，避免落入访问日志与浏览器
历史；本路由免登（与 /api/auth/login 同类），异常交全局处理器转信封。
"""

from flask import Blueprint, request

from app.exceptions import UnauthorizedError
from app.services import sso_service
from app.utils.api_response import success


sso_bp = Blueprint('sso', __name__)


@sso_bp.route('/auth/sso/exchange', methods=['POST'])
def sso_exchange():
    token = request.headers.get('Token', '').strip()
    if not token:
        raise UnauthorizedError('未提供主服务令牌')
    return success(data=sso_service.exchange_sso_token(token))
