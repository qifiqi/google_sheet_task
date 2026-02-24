from datetime import datetime

from sqlalchemy.orm import relationship

from app.extensions import db
import json

class Task(db.Model):
    """任务模型"""
    __tablename__ = 'tasks'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(255), nullable=False)  # 任务名称
    description = db.Column(db.Text)  # 任务描述
    status = db.Column(db.String(20), default='pending', index=True)  # 添加索引，常用于过滤
    task_type = db.Column(db.String(50), default='google_sheet', index=True)  # 添加索引
    
    # 配置信息
    config = db.Column(db.Text)  # JSON格式的配置
    
    # 执行信息
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    current_step = db.Column(db.Integer, default=0)
    total_steps = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)  # 添加索引，常用于排序
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联 - 优化懒加载策略
    logs = db.relationship('TaskLog', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    results = db.relationship('TaskResult', backref='task', lazy='dynamic', cascade='all, delete-orphan')

    # 新增：直接关联到TaskResultReturn（时间序列数据）
    returns_return = db.relationship('TaskResultReturn', backref='task',
                             lazy='dynamic',
                             cascade='all, delete-orphan')

    # 复合索引 - 提升常用查询性能
    __table_args__ = (
        db.Index('idx_status_created', 'status', 'created_at'),  # 按状态和时间查询
        db.Index('idx_type_status', 'task_type', 'status'),  # 按类型和状态查询
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'task_type': self.task_type,
            'config': json.loads(self.config) if self.config else {},
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    def get_progress_percentage(self):
        if self.total_steps == 0:
            return 0
        return round((self.current_step / self.total_steps) * 100, 2)

class TaskLog(db.Model):
    """任务日志模型"""
    __tablename__ = 'task_logs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(36), db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    level = db.Column(db.String(20), default='info', index=True)  # 添加索引
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)  # 添加索引
    
    # 复合索引 - 提升查询性能
    __table_args__ = (
        db.Index('idx_task_timestamp', 'task_id', 'timestamp'),  # 按任务和时间查询
        db.Index('idx_level_timestamp', 'level', 'timestamp'),  # 按级别和时间查询
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }

class TaskResult(db.Model):
    """任务结果模型"""
    __tablename__ = 'task_results'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(36), db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    step_index = db.Column(db.Integer, nullable=False, index=True)  # 添加索引
    parameters = db.Column(db.Text)  # JSON格式的参数
    result = db.Column(db.Text)  # JSON格式的结果
    success = db.Column(db.Boolean, default=True, index=True)  # 添加索引
    error_message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)  # 添加索引

    # 复合索引 - 提升查询性能
    __table_args__ = (
        db.Index('idx_task_step', 'task_id', 'step_index'),  # 按任务和步骤查询
        db.Index('idx_task_timestamp', 'task_id', 'timestamp'),  # 按任务和时间查询
        db.Index('idx_success_timestamp', 'success', 'timestamp'),  # 按成功状态和时间查询
        # db.Index('idx_error_type', 'error_type'),  # 按错误类型查询
    )

    def to_dict(self):
        result_dict = {
            'id': self.id,
            'task_id': self.task_id,
            'step_index': self.step_index,
            'parameters': json.loads(self.parameters) if self.parameters else {},
            'result': json.loads(self.result) if self.result else {},
            'success': self.success,
            'error_message': self.error_message,
            'timestamp': self.timestamp.isoformat()
        }
        # 添加C5增强字段（如果存在）
        if hasattr(self, 'retry_count') and self.retry_count is not None:
            result_dict['retry_count'] = self.retry_count
        if hasattr(self, 'execution_time') and self.execution_time is not None:
            result_dict['execution_time'] = self.execution_time
        if hasattr(self, 'error_type') and self.error_type:
            result_dict['error_type'] = self.error_type
        if hasattr(self, 'http_status') and self.http_status is not None:
            result_dict['http_status'] = self.http_status
        if hasattr(self, 'session_id') and self.session_id:
            result_dict['session_id'] = self.session_id
        if hasattr(self, 'request_id') and self.request_id:
            result_dict['request_id'] = self.request_id
        if hasattr(self, 'retry_round') and self.retry_round is not None:
            result_dict['retry_round'] = self.retry_round
        return result_dict
    
class TaskResultReturn(db.Model):
    __tablename__ = 'task_results_return'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(36), db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    stock_date = db.Column(db.String(50))
    index_return = db.Column(db.Float)
    start_return = db.Column(db.Float)

    def to_dict(self):
        result_dict = {
            'id': self.id,
            'task_id': self.task_id,
            'stock_date': self.stock_date,
            'index_return': self.index_return,
            'start_return': self.start_return,
        }
        return result_dict

class TaskTemplate(db.Model):
    """任务模板模型"""
    __tablename__ = 'task_templates'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, index=True)  # 模板名称
    description = db.Column(db.Text)  # 模板描述
    config = db.Column(db.Text)  # JSON格式的配置
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'config': json.loads(self.config) if self.config else {},
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class SystemConfig(db.Model):
    """系统配置模型"""
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ScheduledTask(db.Model):
    """定时任务模型"""
    __tablename__ = 'scheduled_tasks'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, index=True)  # 任务名称
    description = db.Column(db.Text)  # 任务描述
    cron_expression = db.Column(db.String(100), nullable=False)  # cron表达式
    task_type = db.Column(db.String(50), nullable=False, default='cleanup')  # 任务类型
    task_function = db.Column(db.String(255), nullable=False)  # 执行的函数名
    task_params = db.Column(db.Text)  # JSON格式的任务参数
    is_active = db.Column(db.Boolean, default=True, index=True)  # 是否启用
    last_run_time = db.Column(db.DateTime)  # 上次执行时间
    next_run_time = db.Column(db.DateTime, index=True)  # 下次执行时间
    run_count = db.Column(db.Integer, default=0)  # 执行次数
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 复合索引
    __table_args__ = (
        db.Index('idx_active_next_run', 'is_active', 'next_run_time'),
        db.Index('idx_type_active', 'task_type', 'is_active'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'cron_expression': self.cron_expression,
            'task_type': self.task_type,
            'task_function': self.task_function,
            'task_params': json.loads(self.task_params) if self.task_params else {},
            'is_active': self.is_active,
            'last_run_time': self.last_run_time.isoformat() if self.last_run_time else None,
            'next_run_time': self.next_run_time.isoformat() if self.next_run_time else None,
            'run_count': self.run_count,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
