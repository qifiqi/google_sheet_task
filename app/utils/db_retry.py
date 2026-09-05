"""
数据库重试工具模块
处理暂时性数据库错误的重试逻辑
"""
import time
import random
from functools import wraps
from typing import Callable, Any, Optional
from sqlalchemy.exc import OperationalError
from app.utils.logger import get_logger

logger = get_logger(__name__)


TRANSIENT_DATABASE_ERROR_MARKERS = (
    'database is locked',
    'database table is locked',
    'deadlock',
    'lock wait timeout',
    'could not serialize',
    'serialization failure',
)


class DatabaseLockError(Exception):
    """暂时性数据库冲突在重试后仍未恢复。"""
    pass


def _is_transient_database_error(error: OperationalError) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in TRANSIENT_DATABASE_ERROR_MARKERS)


def _retry_operation(
    operation: Callable,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    exponential_base: float,
    jitter: bool,
    *args,
    **kwargs,
) -> Any:
    for attempt in range(max_attempts):
        try:
            return operation(*args, **kwargs)
        except OperationalError as exc:
            if not _is_transient_database_error(exc):
                raise
            if attempt == max_attempts - 1:
                logger.error("数据库暂时性错误重试失败，已达到最大次数 %s", max_attempts)
                raise DatabaseLockError(
                    f"数据库暂时性错误重试失败: {exc}"
                ) from exc

            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            if jitter:
                delay *= 0.5 + random.random() * 0.5
            logger.warning(
                "数据库暂时性错误，第 %s 次重试，等待 %.2f 秒",
                attempt + 1,
                delay,
            )
            time.sleep(delay)


def db_retry(
    max_attempts: int = 5,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    """
    数据库操作重试装饰器
    处理可恢复的锁冲突或事务序列化失败。
    
    Args:
        max_attempts: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数退避基数
        jitter: 是否添加随机抖动
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return _retry_operation(
                func,
                max_attempts,
                base_delay,
                max_delay,
                exponential_base,
                jitter,
                *args,
                **kwargs,
            )
        return wrapper
    return decorator


def safe_db_operation(
    operation: Callable,
    max_attempts: int = 5,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    *args,
    **kwargs
) -> Any:
    """
    安全执行数据库操作
    
    Args:
        operation: 要执行的数据库操作函数
        max_attempts: 最大重试次数
        base_delay: 基础延迟时间
        max_delay: 最大延迟时间
        *args: 操作函数的参数
        **kwargs: 操作函数的关键字参数
    
    Returns:
        操作结果
    """
    return _retry_operation(
        operation,
        max_attempts,
        base_delay,
        max_delay,
        2.0,
        True,
        *args,
        **kwargs,
    )


class DatabaseRetryManager:
    """数据库重试管理器"""
    
    def __init__(
        self,
        max_attempts: int = 5,
        base_delay: float = 0.1,
        max_delay: float = 2.0,
        exponential_base: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """执行带重试的数据库操作"""
        return safe_db_operation(
            operation,
            self.max_attempts,
            self.base_delay,
            self.max_delay,
            *args,
            **kwargs
        )
    
    def commit_with_retry(self, session):
        """带重试的提交操作"""
        def commit_operation():
            session.commit()
        
        return self.execute_with_retry(commit_operation)
    
    def flush_with_retry(self, session):
        """带重试的刷新操作"""
        def flush_operation():
            session.flush()
        
        return self.execute_with_retry(flush_operation)


# 全局重试管理器实例
db_retry_manager = DatabaseRetryManager()
