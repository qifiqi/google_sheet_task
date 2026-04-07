from datetime import datetime
from enum import Enum
import json

from app.extensions import db


# ==================== RBAC ====================

role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permission.id'), primary_key=True),
)

user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True),
)


class User(db.Model):
    """用户模型"""

    __tablename__ = 'user'
    __table_args__ = {'comment': '用户表'}

    id = db.Column(db.Integer, primary_key=True, comment='用户ID')
    username = db.Column(db.String(80), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    last_login = db.Column(db.DateTime, comment='最后登录时间')
    roles = db.relationship('Role', secondary=user_roles, backref='users')

    def get_permissions(self):
        perms = set()
        for role in self.roles:
            for p in role.permissions:
                perms.add(p.code)
        return perms

    def to_dict(self, include_permissions=False):
        d = {
            'id': self.id,
            'username': self.username,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'roles': [r.to_dict() for r in self.roles],
        }
        if include_permissions:
            d['permissions'] = sorted(self.get_permissions())
        return d


class Role(db.Model):
    """角色模型"""

    __tablename__ = 'role'
    __table_args__ = {'comment': '角色表'}

    id = db.Column(db.Integer, primary_key=True, comment='角色ID')
    name = db.Column(db.String(50), nullable=False, comment='角色名称')
    code = db.Column(db.String(50), unique=True, nullable=False, comment='角色编码，如 admin/operator')
    description = db.Column(db.String(200), comment='角色描述')
    is_system = db.Column(db.Boolean, default=False, comment='是否系统内置角色（不可删除）')
    permissions = db.relationship('Permission', secondary=role_permissions, backref='roles')

    def to_dict(self, include_permissions=False):
        d = {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_system': self.is_system,
        }
        if include_permissions:
            d['permissions'] = [p.to_dict() for p in self.permissions]
        return d


class Permission(db.Model):
    """权限模型"""

    __tablename__ = 'permission'
    __table_args__ = {'comment': '权限表'}

    id = db.Column(db.Integer, primary_key=True, comment='权限ID')
    name = db.Column(db.String(100), nullable=False, comment='权限名称，如"创建任务"')
    code = db.Column(db.String(100), unique=True, nullable=False, comment='权限编码，格式为 资源:操作，如 task:create')
    group = db.Column(db.String(50), nullable=False, comment='权限分组，如 task/config/admin')
    description = db.Column(db.String(200), comment='权限描述')
    route_path = db.Column(db.String(200), comment='关联前端路由路径，如 /admin/config，仅供展示')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'group': self.group,
            'description': self.description,
            'route_path': self.route_path,
        }


# ==================== Enums ====================


class GoogleSheetTableType(str, Enum):
    C3 = "c3"
    C4 = "c4"
    C5 = "c5"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        raw = (value or "").strip().lower()
        if raw == "c31":
            raw = cls.C3.value
        valid_values = {item.value for item in cls}
        if raw in valid_values:
            return raw
        return default

    @classmethod
    def choices(cls):
        return [{"value": item.value, "label": item.value.upper()} for item in cls]


class GoogleSheetTokenTaskType(str, Enum):
    GOOGLE_SHEET = "google_sheet"
    BACKTEST_TRAINING = "backtest_training"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        raw = (value or "").strip().lower()
        valid_values = {item.value for item in cls}
        if raw in valid_values:
            return raw
        return default

    @classmethod
    def choices(cls):
        return [
            {"value": cls.GOOGLE_SHEET.value, "label": "Google Sheet"},
            {"value": cls.BACKTEST_TRAINING.value, "label": "Backtest Training"},
        ]


class Task(db.Model):
    """任务模型"""

    __tablename__ = "tasks"
    __table_args__ = (
        db.Index("idx_status_created", "status", "created_at"),
        db.Index("idx_type_status", "task_type", "status"),
        {"comment": "任务主表"},
    )

    id = db.Column(db.String(36), primary_key=True, comment="任务ID")
    name = db.Column(db.String(255), nullable=False, comment="任务名称")
    description = db.Column(db.Text, comment="任务描述")
    status = db.Column(db.String(20), default="pending", index=True, comment="任务状态")
    task_type = db.Column(db.String(50), default="google_sheet", index=True, comment="任务类型")
    config = db.Column(db.Text, comment="任务配置JSON")
    start_time = db.Column(db.DateTime, comment="开始时间")
    end_time = db.Column(db.DateTime, comment="结束时间")
    current_step = db.Column(db.Integer, default=0, comment="当前步骤")
    total_steps = db.Column(db.Integer, default=0, comment="总步骤数")
    error_message = db.Column(db.Text, comment="错误信息")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    logs = db.relationship("TaskLog", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    results = db.relationship("TaskResult", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    returns_return = db.relationship(
        "TaskResultReturn",
        backref="task",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "task_type": self.task_type,
            "config": json.loads(self.config) if self.config else {},
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_progress_percentage(self):
        if self.total_steps == 0:
            return 0
        return round((self.current_step / self.total_steps) * 100, 2)


class TaskLog(db.Model):
    """任务日志模型"""

    __tablename__ = "task_logs"
    __table_args__ = (
        db.Index("idx_task_logs_task_timestamp", "task_id", "timestamp"),
        db.Index("idx_level_timestamp", "level", "timestamp"),
        {"comment": "任务日志表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="日志ID")
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联任务ID",
    )
    level = db.Column(db.String(20), default="info", index=True, comment="日志级别")
    message = db.Column(db.Text, nullable=False, comment="日志内容")
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True, comment="日志时间")

    def to_dict(self):
        return {
            "id": self.id,
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class TaskResult(db.Model):
    """任务结果模型"""

    __tablename__ = "task_results"
    __table_args__ = (
        db.Index("idx_task_step", "task_id", "step_index"),
        db.Index("idx_task_results_task_timestamp", "task_id", "timestamp"),
        db.Index("idx_success_timestamp", "success", "timestamp"),
        {"comment": "任务结果表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="结果ID")
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联任务ID",
    )
    step_index = db.Column(db.Integer, nullable=False, index=True, comment="步骤序号")
    parameters = db.Column(db.Text, comment="参数JSON")
    result = db.Column(db.Text, comment="结果JSON")
    success = db.Column(db.Boolean, default=True, index=True, comment="是否成功")
    error_message = db.Column(db.Text, comment="错误信息")
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True, comment="结果时间")

    def to_dict(self):
        result_dict = {
            "id": self.id,
            "task_id": self.task_id,
            "step_index": self.step_index,
            "parameters": json.loads(self.parameters) if self.parameters else {},
            "result": json.loads(self.result) if self.result else {},
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
        if hasattr(self, "retry_count") and self.retry_count is not None:
            result_dict["retry_count"] = self.retry_count
        if hasattr(self, "execution_time") and self.execution_time is not None:
            result_dict["execution_time"] = self.execution_time
        if hasattr(self, "error_type") and self.error_type:
            result_dict["error_type"] = self.error_type
        if hasattr(self, "http_status") and self.http_status is not None:
            result_dict["http_status"] = self.http_status
        if hasattr(self, "session_id") and self.session_id:
            result_dict["session_id"] = self.session_id
        if hasattr(self, "request_id") and self.request_id:
            result_dict["request_id"] = self.request_id
        if hasattr(self, "retry_round") and self.retry_round is not None:
            result_dict["retry_round"] = self.retry_round
        return result_dict


class TaskResultReturn(db.Model):
    """任务收益时间序列表"""

    __tablename__ = "task_results_return"
    __table_args__ = ({"comment": "任务收益时间序列表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联任务ID",
    )
    stock_date = db.Column(db.String(50), comment="日期")
    index_return = db.Column(db.Float, comment="指数收益")
    start_return = db.Column(db.Float, comment="策略起始收益")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "stock_date": self.stock_date,
            "index_return": self.index_return,
            "start_return": self.start_return,
        }


class TaskTemplate(db.Model):
    """任务模板模型"""

    __tablename__ = "task_templates"
    __table_args__ = ({"comment": "任务模板表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="模板ID")
    name = db.Column(db.String(255), nullable=False, index=True, comment="模板名称")
    description = db.Column(db.Text, comment="模板描述")
    config = db.Column(db.Text, comment="模板配置JSON")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "config": json.loads(self.config) if self.config else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SystemConfig(db.Model):
    """系统配置模型"""

    __tablename__ = "system_configs"
    __table_args__ = ({"comment": "系统配置表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="配置ID")
    key = db.Column(db.String(100), unique=True, nullable=False, comment="配置键")
    value = db.Column(db.Text, comment="配置值")
    description = db.Column(db.Text, comment="配置说明")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GoogleSheetToken(db.Model):
    """Google Sheet token pool model."""

    __tablename__ = "google_sheet_tokens"
    __table_args__ = (
        db.Index("idx_google_sheet_token_active_usage", "is_active", "current_in_use_count"),
        {"comment": "谷歌 Sheet Token 池表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    name = db.Column(db.String(255), nullable=False, index=True, comment="Token展示名称")
    task_type = db.Column(
        db.String(50),
        nullable=False,
        default=GoogleSheetTokenTaskType.GOOGLE_SHEET.value,
        index=True,
        comment="适用任务类型",
    )
    token_file = db.Column(db.String(500), unique=True, nullable=False, comment="运行时落地文件路径")
    token_context = db.Column(db.Text, nullable=False, comment="Token JSON原文")
    task_usage_count = db.Column(db.Integer, default=0, nullable=False, comment="累计使用次数")
    current_in_use_count = db.Column(db.Integer, default=0, nullable=False, comment="当前占用次数")
    max_usage_count = db.Column(
        db.Integer,
        default=0,
        nullable=False,
        comment="最大同时占用次数，0表示不限制",
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True, comment="是否启用")
    last_used_at = db.Column(db.DateTime, comment="最后使用时间")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def is_available(self):
        return self.is_active and (self.max_usage_count <= 0 or self.current_in_use_count < self.max_usage_count)

    def to_dict(self, include_context: bool = False):
        data = {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type or GoogleSheetTokenTaskType.GOOGLE_SHEET.value,
            "token_file": self.token_file,
            "task_usage_count": self.task_usage_count,
            "current_in_use_count": self.current_in_use_count,
            "max_usage_count": self.max_usage_count,
            "is_active": self.is_active,
            "is_available": self.is_available(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "token_context_size": len(self.token_context or ""),
        }
        if include_context:
            data["token_context"] = self.token_context
        return data


class GoogleSheet(db.Model):
    """Google Sheet registry model."""

    __tablename__ = "google_sheet"
    __table_args__ = (
        db.Index("idx_google_sheet_active_in_use", "is_active", "is_in_use"),
        {"comment": "Google Sheet 表ID配置表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    name = db.Column(db.String(255), nullable=False, index=True, comment="显示名称")
    spreadsheet_id = db.Column(db.String(255), nullable=False, unique=True, index=True, comment="Google Sheet表ID")
    table_type = db.Column(db.String(20), nullable=False, default=GoogleSheetTableType.C3.value, index=True, comment="表类型：c3/c4/c5")
    remark = db.Column(db.Text, comment="备注")
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True, comment="是否启用")
    is_in_use = db.Column(db.Boolean, default=False, nullable=False, index=True, comment="是否使用中")
    current_task_id = db.Column(db.String(36), index=True, comment="当前占用任务ID")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "spreadsheet_id": self.spreadsheet_id,
            "table_type": self.table_type,
            "remark": self.remark,
            "is_active": self.is_active,
            "is_in_use": self.is_in_use,
            "current_task_id": self.current_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ScheduledTask(db.Model):
    """定时任务模型"""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        db.Index("idx_active_next_run", "is_active", "next_run_time"),
        db.Index("idx_type_active", "task_type", "is_active"),
        {"comment": "定时任务表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="定时任务ID")
    name = db.Column(db.String(255), nullable=False, index=True, comment="任务名称")
    description = db.Column(db.Text, comment="任务描述")
    cron_expression = db.Column(db.String(100), nullable=False, comment="Cron表达式")
    task_type = db.Column(db.String(50), nullable=False, default="cleanup", comment="任务类型")
    task_function = db.Column(db.String(255), nullable=False, comment="执行函数名")
    task_params = db.Column(db.Text, comment="任务参数JSON")
    is_active = db.Column(db.Boolean, default=True, index=True, comment="是否启用")
    last_run_time = db.Column(db.DateTime, comment="上次执行时间")
    next_run_time = db.Column(db.DateTime, index=True, comment="下次执行时间")
    run_count = db.Column(db.Integer, default=0, comment="执行次数")
    is_running = db.Column(db.Boolean, default=False, index=True, comment="是否正在执行")
    running_instance_id = db.Column(db.String(100), comment="执行实例ID")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "cron_expression": self.cron_expression,
            "task_type": self.task_type,
            "task_function": self.task_function,
            "task_params": json.loads(self.task_params) if self.task_params else {},
            "is_active": self.is_active,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "next_run_time": self.next_run_time.isoformat() if self.next_run_time else None,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
