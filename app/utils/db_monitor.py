"""
数据库性能监控工具

监控数据库性能指标，包括慢查询、连接池状态、表大小等
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from flask import current_app
from app.extensions import db
from app.models import Task, TaskResult, TaskLog, TaskTemplate, SystemConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseMonitor:
    """数据库性能监控器"""
    
    @staticmethod
    def get_database_size() -> Dict[str, Any]:
        """获取数据库大小信息"""
        try:
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if db_uri.startswith('sqlite'):
                # SQLite数据库
                db_path = db_uri.replace('sqlite:///', '')
                if os.path.exists(db_path):
                    size_bytes = os.path.getsize(db_path)
                    size_mb = size_bytes / (1024 * 1024)
                    
                    return {
                        'type': 'SQLite',
                        'path': db_path,
                        'size_bytes': size_bytes,
                        'size_mb': round(size_mb, 2),
                        'size_human': DatabaseMonitor._format_bytes(size_bytes)
                    }
            else:
                # 其他数据库类型
                return {
                    'type': 'Other',
                    'message': '非SQLite数据库，请使用数据库特定工具查看大小'
                }
                
        except Exception as e:
            logger.error(f"获取数据库大小失败: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def get_table_sizes() -> Dict[str, Dict[str, int]]:
        """获取各表的记录数"""
        try:
            return {
                'tasks': {
                    'count': Task.query.count(),
                    'by_status': {
                        'pending': Task.query.filter_by(status='pending').count(),
                        'running': Task.query.filter_by(status='running').count(),
                        'completed': Task.query.filter_by(status='completed').count(),
                        'error': Task.query.filter_by(status='error').count(),
                        'cancelled': Task.query.filter_by(status='cancelled').count(),
                    }
                },
                'task_results': {
                    'count': TaskResult.query.count(),
                    'success': TaskResult.query.filter_by(success=True).count(),
                    'failed': TaskResult.query.filter_by(success=False).count(),
                },
                'task_logs': {
                    'count': TaskLog.query.count(),
                    'note': '日志已改为文件存储，此表数据为历史遗留'
                },
                'task_templates': {
                    'count': TaskTemplate.query.count(),
                },
                'system_configs': {
                    'count': SystemConfig.query.count(),
                }
            }
        except Exception as e:
            logger.error(f"获取表大小失败: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def get_connection_pool_status() -> Dict[str, Any]:
        """获取连接池状态"""
        try:
            engine = db.engine
            pool = engine.pool
            
            return {
                'pool_size': pool.size(),
                'checked_in': pool.checkedin(),
                'checked_out': pool.checkedout(),
                'overflow': pool.overflow(),
                'total_connections': pool.size() + pool.overflow(),
                'status': 'healthy' if pool.checkedin() > 0 else 'warning'
            }
        except Exception as e:
            logger.error(f"获取连接池状态失败: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def get_recent_activity(hours: int = 24) -> Dict[str, Any]:
        """获取最近的活动统计"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            return {
                'tasks_created': Task.query.filter(Task.created_at >= cutoff_time).count(),
                'tasks_completed': Task.query.filter(
                    Task.status == 'completed',
                    Task.end_time >= cutoff_time
                ).count() if Task.query.filter(Task.end_time != None).count() > 0 else 0,
                'results_generated': TaskResult.query.filter(TaskResult.timestamp >= cutoff_time).count(),
                'period_hours': hours,
                'period_start': cutoff_time.isoformat(),
                'period_end': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取活动统计失败: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def check_indexes() -> Dict[str, List[str]]:
        """检查表索引（仅SQLite）"""
        try:
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if not db_uri.startswith('sqlite'):
                return {'message': '仅支持SQLite数据库'}
            
            indexes = {}
            tables = ['tasks', 'task_results', 'task_logs', 'task_templates', 'system_configs']
            
            for table in tables:
                result = db.session.execute(
                    db.text(f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}'")
                )
                indexes[table] = [row[0] for row in result]
            
            return indexes
        except Exception as e:
            logger.error(f"检查索引失败: {str(e)}")
            return {'error': str(e)}
    
    @staticmethod
    def suggest_optimizations() -> List[Dict[str, str]]:
        """提供优化建议"""
        suggestions = []
        
        try:
            # 检查TaskLog表大小
            tasklog_count = TaskLog.query.count()
            if tasklog_count > 1000:
                suggestions.append({
                    'priority': 'high',
                    'category': '数据清理',
                    'issue': f'TaskLog表有 {tasklog_count:,} 条历史记录',
                    'suggestion': '运行 cleanup_task_logs.py 清理历史日志数据',
                    'benefit': f'预计释放大量空间（约 {tasklog_count * 0.5 / 1024:.1f} MB）'
                })
            
            # 检查已完成任务数量
            completed_count = Task.query.filter_by(status='completed').count()
            if completed_count > 100:
                suggestions.append({
                    'priority': 'medium',
                    'category': '数据归档',
                    'issue': f'已完成任务数量: {completed_count}',
                    'suggestion': '考虑归档或删除旧的已完成任务',
                    'benefit': '减少数据库大小，提升查询速度'
                })
            
            # 检查错误任务
            error_count = Task.query.filter_by(status='error').count()
            if error_count > 20:
                suggestions.append({
                    'priority': 'low',
                    'category': '数据清理',
                    'issue': f'错误任务数量: {error_count}',
                    'suggestion': '清理或修复错误任务',
                    'benefit': '保持数据整洁'
                })
            
            # 检查数据库大小
            db_info = DatabaseMonitor.get_database_size()
            if 'size_mb' in db_info and db_info['size_mb'] > 100:
                suggestions.append({
                    'priority': 'high',
                    'category': '数据库优化',
                    'issue': f"数据库大小: {db_info['size_mb']:.2f} MB",
                    'suggestion': '运行 VACUUM 命令压缩数据库',
                    'benefit': '释放未使用的空间'
                })
            
            # 如果没有问题
            if not suggestions:
                suggestions.append({
                    'priority': 'info',
                    'category': '状态',
                    'issue': '无',
                    'suggestion': '数据库状态良好，无需优化',
                    'benefit': ''
                })
            
        except Exception as e:
            logger.error(f"生成优化建议失败: {str(e)}")
            suggestions.append({
                'priority': 'error',
                'category': '错误',
                'issue': str(e),
                'suggestion': '检查数据库连接',
                'benefit': ''
            })
        
        return suggestions
    
    @staticmethod
    def vacuum_database():
        """执行VACUUM压缩数据库（仅SQLite）"""
        try:
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if not db_uri.startswith('sqlite'):
                return {'success': False, 'message': '仅支持SQLite数据库'}
            
            # 获取压缩前大小
            size_before = DatabaseMonitor.get_database_size()
            
            # 执行VACUUM
            db.session.execute(db.text('VACUUM'))
            db.session.commit()
            
            # 获取压缩后大小
            size_after = DatabaseMonitor.get_database_size()
            
            freed_mb = size_before.get('size_mb', 0) - size_after.get('size_mb', 0)
            
            return {
                'success': True,
                'size_before_mb': size_before.get('size_mb', 0),
                'size_after_mb': size_after.get('size_mb', 0),
                'freed_mb': round(freed_mb, 2),
                'message': f'数据库已压缩，释放 {freed_mb:.2f} MB 空间'
            }
        except Exception as e:
            logger.error(f"VACUUM失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _format_bytes(bytes_size: int) -> str:
        """格式化字节大小为人类可读格式"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"
    
    @staticmethod
    def get_full_report() -> Dict[str, Any]:
        """获取完整的性能报告"""
        return {
            'timestamp': datetime.now().isoformat(),
            'database': DatabaseMonitor.get_database_size(),
            'tables': DatabaseMonitor.get_table_sizes(),
            'connection_pool': DatabaseMonitor.get_connection_pool_status(),
            'recent_activity': DatabaseMonitor.get_recent_activity(),
            'indexes': DatabaseMonitor.check_indexes(),
            'suggestions': DatabaseMonitor.suggest_optimizations()
        }


# 导出
__all__ = ['DatabaseMonitor']

