"""全局错误处理器（见 docs/design/data-layer-refactor/04 §4）。

三层：AppException / HTTPException / 兜底 Exception。
仅 API 路径（request.path 以 /api 开头）返回 JSON 统一信封；
页面路由（/admin、/google-sheet 等）保持 Flask 默认 HTML 错误页。

红线：错误响应绝不携带 str(e) 等内部信息；detail 仅写日志。
"""
from flask import request
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException, InternalServerError

from app.exceptions import AppException
from app.utils.api_response import error
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _is_api_request():
    return request.path.startswith("/api")


def register_error_handlers(app):
    @app.errorhandler(AppException)
    def handle_app_exception(exc):
        log = logger.warning if exc.log_level == "warning" else logger.error
        log("%s: %s | detail=%s", type(exc).__name__, exc.message, exc.detail)
        if not _is_api_request():
            # 页面路由保持 Flask 默认行为：转标准 500 HTML 错误页
            # （errorhandler 返回 None 会被 Flask 视为无效响应，必须显式返回）。
            return InternalServerError(original_exception=exc)
        return error(exc.message, code=exc.code, http_status=exc.http_status)

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        if not _is_api_request():
            # 返回 exc 本身即 Flask 默认处理（HTML 错误页）。
            return exc
        return error(exc.description or exc.name, code=exc.code, http_status=exc.code)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        logger.exception(exc)
        if not _is_api_request():
            return InternalServerError(original_exception=exc)
        # IntegrityError 正常应已被 repository 转换为 ConflictError，此处仅兜底。
        if isinstance(exc, IntegrityError):
            return error("数据冲突，请检查唯一性约束", http_status=409)
        return error("服务器内部错误", http_status=500)
