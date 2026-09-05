from .base import (
    AppException,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServiceError,
    UnauthorizedError,
    ValidationError,
)
from .checkForErrors import checkForErrors
from .c5_exceptions import (
    C5BaseException,
    C5NetworkException,
    C5RateLimitException,
    C5ExecutionException,
    C5ValidationException,
    C5TimeoutException,
    C5DataException
)

__all__ = [
    # 统一异常体系（HTTP 语义；见 docs/design/data-layer-refactor/04 §3）
    'AppException',
    'BadRequestError',
    'ValidationError',
    'UnauthorizedError',
    'ForbiddenError',
    'NotFoundError',
    'ConflictError',
    'RateLimitError',
    'ServiceError',
    # 任务线程域异常（无 HTTP 语义，保持现状，不并入统一体系）
    'checkForErrors',
    'C5BaseException',
    'C5NetworkException',
    'C5RateLimitException',
    'C5ExecutionException',
    'C5ValidationException',
    'C5TimeoutException',
    'C5DataException',
]
