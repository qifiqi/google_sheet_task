"""统一异常体系（全库唯一来源，见 docs/design/data-layer-refactor/04 §3）。

- repositories 只抛 NotFoundError / ConflictError，其余异常原样上抛；
- services 抛语义子类或业务域子类（业务域异常按域放 app/exceptions/ 下分文件）；
- routes 原则上不 catch，由 app/errors.py 全局错误处理器统一转响应信封；
- 任务线程域异常（C5*、RetryableNetworkTaskError、[NETWORK_RETRYABLE] 前缀）
  是执行链语义，无 HTTP 语义，不并入本体系（保持 app/exceptions/c5_exceptions.py 现状）。
"""


class AppException(Exception):
    """应用异常基类。

    message      用户可见消息（可下发客户端）
    code         业务码，默认等于 http_status
    http_status  HTTP 状态码，默认 500
    detail       内部上下文：仅写日志，绝不下发客户端
    log_level    日志级别：4xx → "warning"，5xx → "error"
    """

    http_status = 500

    def __init__(self, message="", *, code=None, http_status=None, detail=None, log_level=None):
        text = message or self.__class__.__name__
        super().__init__(text)
        self.message = text
        self.http_status = http_status if http_status is not None else self.http_status
        self.code = code if code is not None else self.http_status
        self.detail = detail
        self.log_level = log_level or ("warning" if self.http_status < 500 else "error")


class BadRequestError(AppException):
    http_status = 400


class ValidationError(AppException):
    http_status = 400


class UnauthorizedError(AppException):
    http_status = 401


class ForbiddenError(AppException):
    http_status = 403


class NotFoundError(AppException):
    http_status = 404


class ConflictError(AppException):
    http_status = 409


class RateLimitError(AppException):
    http_status = 429


class ServiceError(AppException):
    http_status = 500
