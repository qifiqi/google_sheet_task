"""全局错误处理器（见 docs/design/data-layer-refactor/04 §4）。

三层：AppException / HTTPException / 兜底 Exception。
API 路径返回 JSON 统一信封；页面路由保持 Flask 默认 HTML 错误页。

API 路径判定：路径含 /api 段，或请求 Accept 优先 application/json
（fetch 默认 */* 时同样视为 API）。历史说明：api-model-query-audit/05 拆分后
JSON API 不以 /api 开头的只剩 /admin/api/*（admin_api_bp）等少数正式前缀，
页面路由（浏览器导航）Accept 优先 text/html——Accept 启发式保留，勿删。

红线：错误响应绝不携带 str(e) 等内部信息；detail 仅写日志。
"""
from flask import request
from flask_limiter.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError
from werkzeug import exceptions as http_exceptions
from werkzeug.exceptions import HTTPException, InternalServerError

from app.exceptions import AppException
from app.utils.api_response import error
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _wants_json():
    if request.path.startswith("/api") or "/api/" in request.path:
        return True
    # 浏览器页面导航 Accept 优先 text/html；fetch/axios 优先 application/json 或 */*。
    return request.accept_mimetypes.best_match(
        ["application/json", "text/html"]
    ) == "application/json"


def register_error_handlers(app):
    @app.errorhandler(AppException)
    def handle_app_exception(exc):
        log = logger.warning if exc.log_level == "warning" else logger.error
        log("%s: %s | detail=%s", type(exc).__name__, exc.message, exc.detail)
        if not _wants_json():
            # 页面路由保持 Flask 默认行为：按原状态码渲染标准 HTML 错误页。
            # 返回 HTTPException 实例而非 abort()——处理器内 raise 会破坏处理链。
            exc_cls = http_exceptions.default_exceptions.get(
                exc.http_status, http_exceptions.InternalServerError
            )
            return exc_cls(description=exc.message)
        return error(exc.message, code=exc.code, http_status=exc.http_status)

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        if not _wants_json():
            # 返回 exc 本身即 Flask 默认处理（HTML 错误页）。
            return exc
        return error(exc.description or exc.name, code=exc.code, http_status=exc.code)

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limited(exc):
        # 保护性限流（06 分册）：专用 handler 是为中文文案，
        # 不加也会被 HTTPException handler 兜住转信封。
        logger.warning("限流命中: %s %s", request.method, request.path)
        return error("请求过于频繁，请稍后重试", http_status=429)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        logger.exception(exc)
        if not _wants_json():
            return InternalServerError(original_exception=exc)
        # IntegrityError 正常应已被 repository 转换为 ConflictError，此处仅兜底。
        if isinstance(exc, IntegrityError):
            return error("数据冲突，请检查唯一性约束", http_status=409)
        return error("服务器内部错误", http_status=500)
