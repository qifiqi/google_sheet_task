"""
数据库查询优化工具

提供批量操作、查询优化等功能，减少数据库访问次数，提升性能
"""

from typing import List, Dict, Any, Callable
from app.extensions import db
from app.utils.logger import get_logger
from functools import wraps
import time

logger = get_logger(__name__)


def batch_insert(model_class, data_list: List[Dict[str, Any]], batch_size: int = 100):
    """
    批量插入数据，提升插入性能
    
    Args:
        model_class: 模型类
        data_list: 要插入的数据列表
        batch_size: 每批次插入的数量
        
    Returns:
        插入的记录数
    """
    if not data_list:
        return 0
    
    try:
        total = 0
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            objects = [model_class(**data) for data in batch]
            db.session.bulk_save_objects(objects)
            db.session.commit()
            total += len(batch)
            logger.debug(f"批量插入 {len(batch)} 条记录到 {model_class.__tablename__}")
        
        logger.info(f"批量插入完成，共 {total} 条记录")
        return total
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"批量插入失败: {str(e)}")
        raise


def batch_update(model_class, updates: List[Dict[str, Any]], batch_size: int = 100):
    """
    批量更新数据
    
    Args:
        model_class: 模型类
        updates: 要更新的数据列表，每个字典必须包含 'id' 字段
        batch_size: 每批次更新的数量
        
    Returns:
        更新的记录数
    """
    if not updates:
        return 0
    
    try:
        total = 0
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            db.session.bulk_update_mappings(model_class, batch)
            db.session.commit()
            total += len(batch)
            logger.debug(f"批量更新 {len(batch)} 条记录到 {model_class.__tablename__}")
        
        logger.info(f"批量更新完成，共 {total} 条记录")
        return total
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"批量更新失败: {str(e)}")
        raise


def batch_delete(model_class, ids: List[Any], id_field: str = 'id', batch_size: int = 500):
    """
    批量删除数据
    
    Args:
        model_class: 模型类
        ids: 要删除的ID列表
        id_field: ID字段名
        batch_size: 每批次删除的数量
        
    Returns:
        删除的记录数
    """
    if not ids:
        return 0
    
    try:
        total = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            count = model_class.query.filter(getattr(model_class, id_field).in_(batch_ids)).delete(synchronize_session=False)
            db.session.commit()
            total += count
            logger.debug(f"批量删除 {count} 条记录从 {model_class.__tablename__}")
        
        logger.info(f"批量删除完成，共 {total} 条记录")
        return total
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"批量删除失败: {str(e)}")
        raise


def query_with_pagination(query, page: int = 1, per_page: int = 20):
    """
    分页查询优化
    
    Args:
        query: SQLAlchemy查询对象
        page: 页码
        per_page: 每页记录数
        
    Returns:
        (items, total, pages) 元组
    """
    try:
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total, pagination.pages
    except Exception as e:
        logger.error(f"分页查询失败: {str(e)}")
        return [], 0, 0


def get_or_create(model_class, defaults: Dict[str, Any] = None, **kwargs):
    """
    获取或创建记录，避免重复查询
    
    Args:
        model_class: 模型类
        defaults: 创建时的默认值
        **kwargs: 查询条件
        
    Returns:
        (instance, created) 元组
    """
    try:
        instance = model_class.query.filter_by(**kwargs).first()
        
        if instance:
            return instance, False
        
        # 创建新记录
        params = dict(kwargs)
        if defaults:
            params.update(defaults)
        
        instance = model_class(**params)
        db.session.add(instance)
        db.session.commit()
        
        return instance, True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"get_or_create 失败: {str(e)}")
        raise


def query_in_batches(query, batch_size: int = 1000):
    """
    批量查询生成器，避免一次性加载大量数据到内存
    
    Args:
        query: SQLAlchemy查询对象
        batch_size: 每批次的大小
        
    Yields:
        每批次的记录列表
    """
    offset = 0
    while True:
        batch = query.limit(batch_size).offset(offset).all()
        if not batch:
            break
        yield batch
        offset += batch_size


def measure_query_time(func: Callable) -> Callable:
    """
    装饰器：测量查询执行时间
    
    Usage:
        @measure_query_time
        def my_query():
            return Task.query.all()
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        if elapsed > 1.0:  # 超过1秒的查询记录警告
            logger.warning(f"慢查询检测: {func.__name__} 耗时 {elapsed:.2f}秒")
        else:
            logger.debug(f"查询 {func.__name__} 耗时 {elapsed:.3f}秒")
        
        return result
    return wrapper


class QueryOptimizer:
    """查询优化器类"""
    
    @staticmethod
    def prefetch_related(query, *relationships):
        """
        预加载关联关系，避免N+1查询
        
        Args:
            query: SQLAlchemy查询对象
            *relationships: 要预加载的关系名称
            
        Returns:
            优化后的查询对象
        """
        from sqlalchemy.orm import joinedload
        
        for rel in relationships:
            query = query.options(joinedload(rel))
        
        return query
    
    @staticmethod
    def select_only(query, *columns):
        """
        只查询指定列，减少数据传输
        
        Args:
            query: SQLAlchemy查询对象
            *columns: 要查询的列
            
        Returns:
            优化后的查询对象
        """
        return query.with_entities(*columns)
    
    @staticmethod
    def exists_check(model_class, **filters):
        """
        快速检查记录是否存在（不加载数据）
        
        Args:
            model_class: 模型类
            **filters: 查询条件
            
        Returns:
            bool: 是否存在
        """
        return db.session.query(
            model_class.query.filter_by(**filters).exists()
        ).scalar()
    
    @staticmethod
    def count_fast(query):
        """
        快速计数（使用count()而不是加载所有数据）
        
        Args:
            query: SQLAlchemy查询对象
            
        Returns:
            int: 记录数
        """
        from sqlalchemy import func
        return query.with_entities(func.count()).scalar()


# 导出常用函数
__all__ = [
    'batch_insert',
    'batch_update',
    'batch_delete',
    'query_with_pagination',
    'get_or_create',
    'query_in_batches',
    'measure_query_time',
    'QueryOptimizer',
]

