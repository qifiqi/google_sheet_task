"""
数据库操作工具模块
提供事务管理等功能

2026-09 清理：safe_delete / safe_update / safe_create / DatabaseManager 已随
数据层重构退役（调用点清零），统一改用 app/repositories/ 仓储方法。
"""
import functools
from sqlalchemy.exc import IntegrityError, OperationalError
from app.extensions import db
from app.utils.logger import get_logger
from app.utils.db_retry import safe_db_operation, DatabaseLockError

logger = get_logger(__name__)


def transaction_required(func):
    """
    数据库事务装饰器
    自动处理事务提交、回滚和异常处理；提交走 safe_db_operation 重试。

    注意：重试只保护提交动作本身（safe_db_operation），不重放函数体内的写操作；
    需要可重放的提交请用 repository 的 commit_with_retry(operation)。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            # 使用重试逻辑提交事务
            safe_db_operation(db.session.commit)
            return result
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"数据库完整性错误: {str(e)}")
            raise
        except (OperationalError, DatabaseLockError) as e:
            db.session.rollback()
            logger.error(f"数据库操作错误: {str(e)}")
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"数据库操作异常: {str(e)}")
            raise
    return wrapper
