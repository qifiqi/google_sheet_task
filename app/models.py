from datetime import date, datetime
from enum import Enum
import json

from sqlalchemy import event
from sqlalchemy.orm import foreign

from app.extensions import db
from app.utils.market import MARKET_DEFAULT_COMMISSIONS, MARKET_LABELS


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


# ==================== Enums ====================


class GoogleSheetTableType(str, Enum):
    C3 = "c3"
    C4 = "c4"
    C5 = "c5"
    C7 = "c7"
    BACKTEST_TRAINING = "backtest_training"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        """将 Sheet 表类型别名归一为系统枚举值。"""
        raw = (value or "").strip().lower()
        if raw == "c31":
            raw = cls.C3.value
        valid_values = {item.value for item in cls}
        if raw in valid_values:
            return raw
        return default

    @classmethod
    def choices(cls):
        """返回可供前端选择的 Sheet 表类型列表。"""
        labels = {
            cls.C3: "C3",
            cls.C4: "C4",
            cls.C5: "C5",
            cls.C7: "C7",
            cls.BACKTEST_TRAINING: "单品回测",
        }
        return [{"value": item.value, "label": labels[item]} for item in cls]


class StockMarketType(str, Enum):
    CN = "cn"
    EN = "en"
    CA = "ca"
    KR = "kr"
    JP = "jp"
    HK = "hk"
    UK = "uk"
    FR = "fr"
    DE = "de"
    SG = "sg"
    AU = "au"
    MY = "my"

    @classmethod
    def choices(cls):
        return [
            {
                "value": item.value,
                "label": MARKET_LABELS[item.value],
                "default_commission": MARKET_DEFAULT_COMMISSIONS[item.value],
            }
            for item in cls
        ]


class GoogleSheetTokenTaskType(str, Enum):
    GOOGLE_SHEET = "google_sheet"
    BACKTEST_TRAINING = "backtest_training"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        """将 Token 适用任务类型别名归一为系统枚举值。"""
        raw = (value or "").strip().lower()
        valid_values = {item.value for item in cls}
        if raw in valid_values:
            return raw
        return default

    @classmethod
    def choices(cls):
        """返回可供前端选择的 Token 任务类型列表。"""
        return [
            {"value": cls.GOOGLE_SHEET.value, "label": "Google Sheet"},
            {"value": cls.BACKTEST_TRAINING.value, "label": "Backtest Training"},
        ]


def google_sheet_registry_scope(table_type: str | None) -> str:
    """根据 Sheet 表类型计算注册表唯一性作用域。"""
    normalized = GoogleSheetTableType.normalize(table_type, GoogleSheetTableType.C3.value)
    if normalized in {
        GoogleSheetTableType.C3.value,
        GoogleSheetTableType.C4.value,
        GoogleSheetTableType.C5.value,
        GoogleSheetTableType.C7.value,
    }:
        return "c_series"
    return normalized


def summary_market_type(stock_code: str | None) -> str:
    """根据股票代码格式推断汇总结果所属市场。"""
    return "cn" if str(stock_code or "").strip().isdigit() else "us"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        """将任务状态别名归一为系统枚举值。"""
        raw = (value or "").strip().lower()
        valid_values = {item.value for item in cls}
        if raw in valid_values:
            return raw
        return default

    @classmethod
    def choices(cls):
        """返回全部任务状态的前端选项。"""
        labels = {
            cls.PENDING: "待执行",
            cls.RUNNING: "运行中",
            cls.COMPLETED: "已完成",
            cls.CANCELLED: "已取消",
            cls.ERROR: "错误",
        }
        return [{"value": item.value, "label": labels[item]} for item in cls]

    @classmethod
    def editable_choices(cls):
        """返回允许人工编辑的任务状态选项。"""
        return [
            item for item in cls.choices()
            if item["value"] in {cls.PENDING.value, cls.COMPLETED.value, cls.CANCELLED.value, cls.ERROR.value}
        ]


class TaskType(str, Enum):
    GOOGLE_SHEET = "google_sheet"
    GOOGLE_SHEET_C4 = "google_sheet_C4"
    GOOGLE_SHEET_C5 = "google_sheet_C5"
    GOOGLE_SHEET_C7 = "google_sheet_C7"
    BACKTEST_TRAINING = "backtest_training"
    BACKTEST_MULTI_PRODUCT = "backtest_multi_product"
    MODEL_SUMMARY_REBUILD = "model_summary_rebuild"

    @classmethod
    def normalize(cls, value: str | None, default: str | None = None) -> str | None:
        """将任务类型别名归一为系统枚举值。"""
        raw = (value or "").strip()
        normalized = raw.lower()
        aliases = {
            "google_sheet": cls.GOOGLE_SHEET.value,
            "google_sheet_c3": cls.GOOGLE_SHEET.value,
            "google_sheet_c31": cls.GOOGLE_SHEET.value,
            "google_sheet_c4": cls.GOOGLE_SHEET_C4.value,
            "google_sheet_c5": cls.GOOGLE_SHEET_C5.value,
            "google_sheet_c7": cls.GOOGLE_SHEET_C7.value,
            "backtest": cls.BACKTEST_TRAINING.value,
            "backtest_training": cls.BACKTEST_TRAINING.value,
            "backtest_multi": cls.BACKTEST_MULTI_PRODUCT.value,
            "multi_product_backtest": cls.BACKTEST_MULTI_PRODUCT.value,
            "backtest_multi_product": cls.BACKTEST_MULTI_PRODUCT.value,
            "model_summary_rebuild": cls.MODEL_SUMMARY_REBUILD.value,
        }
        return aliases.get(normalized, default)

    @classmethod
    def choices(cls, include_system=False):
        """返回任务类型选项；可选择包含内部系统任务。"""
        labels = {
            cls.GOOGLE_SHEET: "Google Sheet C3",
            cls.GOOGLE_SHEET_C4: "Google Sheet C4",
            cls.GOOGLE_SHEET_C5: "Google Sheet C5",
            cls.GOOGLE_SHEET_C7: "Google Sheet C7",
            cls.BACKTEST_TRAINING: "单品回测",
            cls.BACKTEST_MULTI_PRODUCT: "多品回测",
            cls.MODEL_SUMMARY_REBUILD: "汇总索引重建",
        }
        system_types = {cls.MODEL_SUMMARY_REBUILD}
        return [
            {"value": item.value, "label": labels[item]}
            for item in cls
            if include_system or item not in system_types
        ]


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
    returns_return = db.relationship(
        "TaskResultReturn",
        primaryjoin=lambda: Task.id == foreign(TaskResultReturn.task_id),
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


class TaskResultReturn(db.Model):
    """任务收益时间序列表"""

    __tablename__ = "t_param_task_results_return"
    __table_args__ = ({"comment": "任务收益时间序列表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    task_id = db.Column(
        db.String(36),
        nullable=False,
        index=True,
        comment="关联任务ID",
    )
    stock_code = db.Column(db.String(20), nullable=False, default="UNKNOWN", index=True)
    stock_name = db.Column(db.String(20), nullable=False, default="未知股票", index=True)
    start_return_date = db.Column(
        db.Date,
        nullable=False,
        default=date(1970, 1, 1),
        comment="策略起始日期",
    )
    end_return_date = db.Column(
        db.Date,
        nullable=False,
        default=date(1970, 1, 1),
        comment="策略结束日期",
    )
    return_length = db.Column(db.Integer, nullable=False, default=0, comment="收益列长度")
    stock_date = db.Column(db.Text, comment="日期")
    index_return = db.Column(db.Text, comment="指数收益")
    start_return = db.Column(db.Text, comment="策略起始收益")

    def to_dict(self):
        """将任务收益序列记录转换为字典。"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "start_return_date": self.start_return_date.isoformat() if self.start_return_date else None,
            "end_return_date": self.end_return_date.isoformat() if self.end_return_date else None,
            "return_length": self.return_length,
            "stock_date": self.stock_date,
            "index_return": self.index_return,
            "start_return": self.start_return,
        }


class BacktestProductResultCache(db.Model):
    """Same-batch reusable result for fixed multi-product backtest products."""

    __tablename__ = "t_param_backtest_product_result_cache"
    __table_args__ = (
        db.UniqueConstraint("batch_id", "cache_key", name="uk_backtest_product_cache_batch_key"),
        {"comment": "多品回测固定产品同批结果缓存表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    batch_id = db.Column(db.String(64), nullable=False, comment="同批创建ID")
    cache_key = db.Column(db.String(64), nullable=False, comment="固定产品结果缓存键")
    result_json = db.Column(db.Text, nullable=False, comment="结果JSON")
    returns_json = db.Column(db.Text, comment="收益曲线JSON")
    source_task_id = db.Column(db.String(36), comment="来源任务ID")
    source_step_index = db.Column(db.Integer, comment="来源步骤序号")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")

    def to_dict(self):
        """将多品回测缓存记录转换为字典。"""
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "cache_key": self.cache_key,
            "result_json": self.result_json,
            "returns_json": self.returns_json,
            "source_task_id": self.source_task_id,
            "source_step_index": self.source_step_index,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BacktestSheetRunLock(db.Model):
    """Database-backed per-spreadsheet run lock for backtest tasks."""

    __tablename__ = "t_param_backtest_sheet_run_locks"
    __table_args__ = (
        db.UniqueConstraint("spreadsheet_id", name="uk_backtest_sheet_run_locks_spreadsheet_id"),
        {"comment": "回测任务 Google Sheet 运行锁表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    spreadsheet_id = db.Column(db.String(255), nullable=False, comment="Google Sheet 表ID")
    task_id = db.Column(db.String(36), nullable=False, index=True, comment="持锁任务ID")
    task_type = db.Column(db.String(50), nullable=False, comment="任务类型")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="更新时间",
    )

    def to_dict(self):
        """将回测 Sheet 运行锁转换为字典。"""
        return {
            "id": self.id,
            "spreadsheet_id": self.spreadsheet_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskResultSummaryIndex(db.Model):
    """任务结果汇总查询索引表。"""

    __tablename__ = "t_param_task_result_summary_index"
    __table_args__ = (
        db.UniqueConstraint("task_result_id", "model_key", name="uk_result_summary_result_model"),
        db.Index("idx_result_summary_type_stock_best", "task_type", "stock_code", "is_best"),
        db.Index("idx_result_summary_task_best", "task_id", "is_best"),
        db.Index("idx_result_summary_best_metric", "best_metric_value"),
        db.Index("idx_result_summary_created_at", "created_at"),
        db.Index("idx_result_summary_period_key", "period_key"),
        db.Index("idx_result_summary_type_market_best", "task_type", "market_type", "is_best"),
        {"comment": "任务结果汇总查询索引表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    task_id = db.Column(db.String(36), nullable=False, comment="关联任务ID")
    task_result_id = db.Column(db.Integer, nullable=False, comment="关联任务结果ID")
    task_type = db.Column(db.String(50), nullable=False, comment="任务类型")
    task_name = db.Column(db.String(255), comment="任务名称")
    stock_code = db.Column(db.String(64), comment="股票代码/产品代码")
    stock_name = db.Column(db.String(255), comment="股票名称/产品名称")
    market_type = db.Column(db.String(8), nullable=False, default="us", comment="股票市场类型 cn/us")
    model_key = db.Column(db.String(255), nullable=False, default="default", comment="模型键")
    model_name = db.Column(db.String(255), comment="模型名称")
    year_label = db.Column(db.String(64), comment="年份或区间标签")
    period_key = db.Column(db.String(32), comment="标准化年份/区间筛选键")
    kline_range = db.Column(db.String(128), comment="K线区间")
    parameter_summary = db.Column(db.Text, comment="参数摘要")
    best_metric_name = db.Column(db.String(100), comment="最优指标名称")
    best_metric_value = db.Column(db.Float, comment="最优指标值")
    metrics_json = db.Column(db.Text, comment="汇总指标JSON")
    is_best = db.Column(db.Boolean, default=False, nullable=False, index=True, comment="是否当前分组最优")
    result_timestamp = db.Column(db.DateTime, index=True, comment="原始结果时间")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    task = db.relationship(
        "Task",
        primaryjoin=lambda: foreign(TaskResultSummaryIndex.task_id) == Task.id,
        backref=db.backref("summary_indexes", lazy="dynamic"),
    )
    task_result = db.relationship(
        "TaskResult",
        primaryjoin=lambda: foreign(TaskResultSummaryIndex.task_result_id) == TaskResult.id,
        backref=db.backref("summary_indexes", lazy="dynamic"),
    )

    def to_dict(self):
        """将任务结果汇总索引转换为包含指标的字典。"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_result_id": self.task_result_id,
            "task_type": self.task_type,
            "task_name": self.task_name,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "model_key": self.model_key,
            "model_name": self.model_name,
            "year_label": self.year_label,
            "period_key": self.period_key,
            "kline_range": self.kline_range,
            "parameter_summary": _json_object_or_empty(self.parameter_summary),
            "best_metric_name": self.best_metric_name,
            "best_metric_value": self.best_metric_value,
            "metrics": _normalize_summary_metrics(_json_object_or_empty(self.metrics_json)),
            "is_best": self.is_best,
            "result_timestamp": self.result_timestamp.isoformat() if self.result_timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StockMetadata(db.Model):
    """股票元数据表。"""

    __tablename__ = "t_param_stock_metadata"
    __table_args__ = (
        db.UniqueConstraint("stock_code", "market_type", name="uk_stock_metadata_code_market_type"),
        {"comment": "股票元数据表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    stock_code = db.Column(db.String(64), nullable=False, comment="股票代码")
    stock_name = db.Column(db.String(255), nullable=False, default="", comment="股票名称")
    market_type = db.Column(db.String(20), nullable=False, default="", comment="业务市场类型 cn/us")
    exchange_market = db.Column(db.String(50), comment="交易市场/东方财富 market")
    security_type_name = db.Column(db.String(100), comment="证券类型名称")
    source = db.Column(db.String(50), comment="数据来源")
    raw_json = db.Column(db.Text, comment="原始搜索结果 JSON")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def to_dict(self):
        """将股票元数据转换为字典。"""
        return {
            "id": self.id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "market_type": self.market_type,
            "exchange_market": self.exchange_market,
            "security_type_name": self.security_type_name,
            "source": self.source,
            "raw": _json_object_or_empty(self.raw_json),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskTemplate(db.Model):
    """任务模板模型"""

    __tablename__ = "t_param_task_templates"
    __table_args__ = ({"comment": "任务模板表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="模板ID")
    name = db.Column(db.String(255), nullable=False, comment="模板名称")
    description = db.Column(db.Text, comment="模板描述")
    config = db.Column(db.Text, comment="模板配置JSON")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        """将任务模板及其配置转换为字典。"""
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

    __tablename__ = "t_param_system_configs"
    __table_args__ = ({"comment": "系统配置表"},)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="配置ID")
    key = db.Column(db.String(100), unique=True, nullable=False, comment="配置键")
    value = db.Column(db.Text, comment="配置值")
    description = db.Column(db.Text, comment="配置说明")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        """将系统配置转换为字典。"""
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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


class GoogleSheetToken(db.Model):
    """Google Sheet token pool model."""

    __tablename__ = "t_param_google_sheet_tokens"
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
    is_active = db.Column(db.Boolean, default=True, nullable=False, comment="是否启用")
    last_used_at = db.Column(db.DateTime, comment="最后使用时间")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def is_available(self):
        """判断 Token 是否启用且未超过并发使用上限。"""
        return self.is_active and (self.max_usage_count <= 0 or self.current_in_use_count < self.max_usage_count)

    def to_dict(self, include_context: bool = False):
        """将 Token 转换为字典，默认不暴露敏感上下文。"""
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

    __tablename__ = "t_param_google_sheet"
    __table_args__ = (
        db.UniqueConstraint(
            "spreadsheet_id",
            "registry_scope",
            name="uk_google_sheet_spreadsheet_registry_scope",
        ),
        db.Index("idx_google_sheet_active_in_use", "is_active", "is_in_use"),
        {"comment": "Google Sheet 表ID配置表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    name = db.Column(db.String(255), nullable=False, index=True, comment="显示名称")
    spreadsheet_id = db.Column(db.String(255), nullable=False, index=True, comment="Google Sheet表ID")
    table_type = db.Column(db.String(20), nullable=False, default=GoogleSheetTableType.C3.value, index=True, comment="表类型：c3/c4/c5/c7/backtest_training")
    registry_scope = db.Column(db.String(32), nullable=False, comment="表类型唯一性分组")
    remark = db.Column(db.Text, comment="备注")
    is_active = db.Column(db.Boolean, default=True, nullable=False, comment="是否启用")
    is_in_use = db.Column(db.Boolean, default=False, nullable=False, index=True, comment="是否使用中")
    current_task_id = db.Column(db.String(36), index=True, comment="当前占用任务ID")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def to_dict(self):
        """将 Google Sheet 注册记录转换为字典。"""
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


@event.listens_for(GoogleSheet, "before_insert")
@event.listens_for(GoogleSheet, "before_update")
def _sync_google_sheet_registry_scope(_mapper, _connection, target):
    """在 Sheet 写入前同步由表类型推导的注册作用域。"""
    target.registry_scope = google_sheet_registry_scope(target.table_type)


@event.listens_for(TaskResultSummaryIndex, "before_insert")
@event.listens_for(TaskResultSummaryIndex, "before_update")
def _sync_summary_market_type(_mapper, _connection, target):
    """在汇总索引写入前同步由股票代码推导的市场类型。"""
    target.market_type = summary_market_type(target.stock_code)


class ScheduledTask(db.Model):
    """定时任务模型"""

    __tablename__ = "t_param_scheduled_tasks"
    __table_args__ = (
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
    next_run_time = db.Column(db.DateTime, comment="下次执行时间")
    run_count = db.Column(db.Integer, default=0, comment="执行次数")
    is_running = db.Column(db.Boolean, default=False, comment="是否正在执行")
    running_instance_id = db.Column(db.String(100), comment="执行实例ID")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self):
        """将定时任务转换为包含任务参数的字典。"""
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
