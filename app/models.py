from datetime import datetime
import json

from sqlalchemy.orm import foreign

from app.extensions import db


def _json_object_or_empty(raw):
    """将 JSON 文本安全解析为对象，失败时返回空字典。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_summary_metrics(metrics):
    """规范化汇总指标字段，保证其可安全序列化。"""
    if not isinstance(metrics, dict):
        return {}
    normalized = dict(metrics)
    if "start_sharpe_ratio" not in normalized and "sharpe_ratio" in normalized:
        normalized["start_sharpe_ratio"] = normalized["sharpe_ratio"]
    return normalized


# ==================== RBAC ====================

role_permissions = db.Table('t_param_role_permissions',
    db.Column('role_id', db.Integer, primary_key=True),
    db.Column('permission_id', db.Integer, primary_key=True),
)

user_roles = db.Table('t_param_user_roles',
    db.Column('user_id', db.Integer, primary_key=True),
    db.Column('role_id', db.Integer, primary_key=True),
)


class User(db.Model):
    """用户模型"""

    __tablename__ = 't_param_user'
    __table_args__ = {'comment': '用户表'}

    id = db.Column(db.Integer, primary_key=True, comment='用户ID')
    username = db.Column(db.String(80), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    mobile = db.Column(db.String(32), comment='手机号')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    is_alert_oncall = db.Column(db.Boolean, default=False, nullable=False, comment='是否参与告警值班')
    token_version = db.Column(db.Integer, default=0, nullable=False, comment='JWT 会话版本号')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    last_login = db.Column(db.DateTime, comment='最后登录时间')
    roles = db.relationship(
        'Role',
        secondary=user_roles,
        primaryjoin=lambda: User.id == foreign(user_roles.c.user_id),
        secondaryjoin=lambda: Role.id == foreign(user_roles.c.role_id),
        backref='users',
    )

    def get_permissions(self):
        """汇总用户所有角色关联的权限编码。"""
        perms = set()
        for role in self.roles:
            for p in role.permissions:
                perms.add(p.code)
        return perms

    def to_dict(self, include_permissions=False):
        """将用户模型转换为接口或模板可使用的字典。"""
        d = {
            'id': self.id,
            'username': self.username,
            'mobile': self.mobile,
            'is_active': self.is_active,
            'is_alert_oncall': self.is_alert_oncall,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'roles': [r.to_dict() for r in self.roles],
        }
        if include_permissions:
            d['permissions'] = sorted(self.get_permissions())
        return d


class Role(db.Model):
    """角色模型"""

    __tablename__ = 't_param_role'
    __table_args__ = {'comment': '角色表'}

    id = db.Column(db.Integer, primary_key=True, comment='角色ID')
    name = db.Column(db.String(50), nullable=False, comment='角色名称')
    code = db.Column(db.String(50), unique=True, nullable=False, comment='角色编码，如 admin/operator')
    description = db.Column(db.String(200), comment='角色描述')
    is_system = db.Column(db.Boolean, default=False, comment='是否系统内置角色（不可删除）')
    permissions = db.relationship(
        'Permission',
        secondary=role_permissions,
        primaryjoin=lambda: Role.id == foreign(role_permissions.c.role_id),
        secondaryjoin=lambda: Permission.id == foreign(role_permissions.c.permission_id),
        backref='roles',
    )

    def to_dict(self, include_permissions=False):
        """将角色及可选权限信息转换为字典。"""
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

    __tablename__ = 't_param_permission'
    __table_args__ = {'comment': '权限表'}

    id = db.Column(db.Integer, primary_key=True, comment='权限ID')
    name = db.Column(db.String(100), nullable=False, comment='权限名称，如"创建任务"')
    code = db.Column(db.String(100), unique=True, nullable=False, comment='权限编码，格式为 资源:操作，如 task:create')
    group = db.Column(db.String(50), nullable=False, comment='权限分组，如 task/config/admin')
    description = db.Column(db.String(200), comment='权限描述')
    route_path = db.Column(db.String(200), comment='关联前端路由路径，如 /admin/config，仅供展示')

    def to_dict(self):
        """将权限模型转换为字典。"""
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'group': self.group,
            'description': self.description,
            'route_path': self.route_path,
        }


from app.domain_constants import (
    GoogleSheetTableType,
    GoogleSheetTokenTaskType,
    StockMarketType,
    TaskStatus,
    TaskType,
)

class Task(db.Model):
    """任务模型"""

    __tablename__ = "t_param_tasks"
    __table_args__ = (
        db.Index("idx_status_created", "status", "created_at"),
        db.Index("idx_type_status", "task_type", "status"),
        {"comment": "任务主表"},
    )

    id = db.Column(db.String(36), primary_key=True, comment="任务ID")
    name = db.Column(db.String(255), nullable=False, comment="任务名称")
    description = db.Column(db.Text, comment="任务描述")
    status = db.Column(db.String(20), default="pending", comment="任务状态")
    task_type = db.Column(db.String(50), default="google_sheet", comment="任务类型")
    config = db.Column(db.Text, comment="任务配置JSON")
    created_by_user_id = db.Column(db.Integer, index=True, comment="创建人用户ID")
    start_time = db.Column(db.DateTime, comment="开始时间")
    end_time = db.Column(db.DateTime, comment="结束时间")
    current_step = db.Column(db.Integer, default=0, comment="当前步骤")
    total_steps = db.Column(db.Integer, default=0, comment="总步骤数")
    error_message = db.Column(db.Text, comment="错误信息")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    logs = db.relationship(
        "TaskLog",
        primaryjoin=lambda: Task.id == foreign(TaskLog.task_id),
        backref="task",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    results = db.relationship(
        "TaskResult",
        primaryjoin=lambda: Task.id == foreign(TaskResult.task_id),
        backref="task",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    created_by = db.relationship(
        "User",
        primaryjoin=lambda: foreign(Task.created_by_user_id) == User.id,
        foreign_keys=lambda: [Task.created_by_user_id],
    )

    def to_dict(self):
        """将任务模型转换为包含配置解析结果的字典。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "task_type": self.task_type,
            "config": json.loads(self.config) if self.config else {},
            "created_by_user_id": self.created_by_user_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_progress_percentage(self):
        """按已完成步骤与总步骤计算任务百分比进度。"""
        if self.total_steps == 0:
            return 0
        return round((self.current_step / self.total_steps) * 100, 2)


class TaskLog(db.Model):
    """任务日志模型"""

    # 即使旧库尚未完成迁移，也要避免把整条收益序列写入日志字段。
    MAX_MESSAGE_LENGTH = 4000

    __tablename__ = "t_param_task_logs"
    __table_args__ = (
        db.Index("idx_task_logs_task_timestamp", "task_id", "timestamp"),
        {"comment": "任务日志表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="日志ID")
    task_id = db.Column(
        db.String(36),
        nullable=False,
        comment="关联任务ID",
    )
    level = db.Column(db.String(20), default="info", comment="日志级别")
    message = db.Column(db.Text, nullable=False, comment="日志内容")
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True, comment="日志时间")

    @classmethod
    def normalize_message(cls, message) -> str:
        """将日志内容限制在可控长度，避免大结果或异常堆栈撑爆数据库字段。"""
        text = "" if message is None else str(message)
        if len(text) <= cls.MAX_MESSAGE_LENGTH:
            return text
        suffix = "...（日志已截断）"
        return text[: cls.MAX_MESSAGE_LENGTH - len(suffix)] + suffix

    def to_dict(self):
        """将任务日志转换为接口响应字典。"""
        return {
            "id": self.id,
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class TaskResult(db.Model):
    """任务结果模型"""

    __tablename__ = "t_param_task_results"
    __table_args__ = (
        db.Index("idx_task_step", "task_id", "step_index"),
        db.Index("idx_task_results_task_timestamp", "task_id", "timestamp"),
        db.Index("idx_success_timestamp", "success", "timestamp"),
        {"comment": "任务结果表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="结果ID")
    task_id = db.Column(
        db.String(36),
        nullable=False,
        comment="关联任务ID",
    )
    step_index = db.Column(db.Integer, nullable=False, comment="步骤序号")
    parameters = db.Column(db.Text, comment="参数JSON")
    result = db.Column(db.Text, comment="结果JSON")
    return_series_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
        comment="收益曲线ID",
    )
    success = db.Column(db.Boolean, default=True, comment="是否成功")
    error_message = db.Column(db.Text, comment="错误信息")
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True, comment="结果时间")

    def to_dict(self):
        """将任务结果及 JSON 字段转换为接口响应字典。"""
        result_dict = {
            "id": self.id,
            "task_id": self.task_id,
            "step_index": self.step_index,
            "parameters": json.loads(self.parameters) if self.parameters else {},
            "result": json.loads(self.result) if self.result else {},
            "return_series_id": self.return_series_id,
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


class NavigationMenuItem(db.Model):
    """侧边栏导航菜单项"""

    __tablename__ = "t_param_navigation_menu_items"
    __table_args__ = (
        db.Index("idx_navigation_menu_parent_sort", "parent_key", "sort_order"),
        {"comment": "侧边栏导航菜单表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="菜单ID")
    key = db.Column(db.String(100), unique=True, nullable=False, comment="菜单唯一键")
    label = db.Column(db.String(100), nullable=False, comment="菜单名称")
    path = db.Column(db.String(255), comment="前端路由路径")
    permission = db.Column(db.String(100), comment="访问该菜单所需权限编码")
    parent_key = db.Column(db.String(100), comment="父级菜单key，空表示顶级")
    sort_order = db.Column(db.Integer, default=0, nullable=False, comment="排序值")
    is_visible = db.Column(db.Boolean, default=True, nullable=False, index=True, comment="是否显示")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self, include_children=False):
        """将导航菜单项转换为字典，并可附带子节点。"""
        data = {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            "path": self.path,
            "permission": self.permission,
            "parent_key": self.parent_key,
            "sort_order": self.sort_order,
            "is_visible": self.is_visible,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_children:
            data["children"] = []
        return data
