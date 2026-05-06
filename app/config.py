import os
import secrets
from pathlib import Path


def _get_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes', 'on')


def _get_int(name, default):
    return int(os.environ.get(name, default))


BASE_DIR = Path(__file__).parent.parent
INSTANCE_DIR = BASE_DIR / 'instance'
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'
CONFIG_DIR = BASE_DIR / 'config'


def _resolve_database_url(default_url):
    database_url = os.environ.get('DATABASE_URL') or default_url

    if database_url.startswith('sqlite:///'):
        sqlite_path = database_url.replace('sqlite:///', '', 1)
        sqlite_path_obj = Path(sqlite_path)
        if not sqlite_path_obj.is_absolute():
            sqlite_path_obj = BASE_DIR / sqlite_path_obj
        database_url = f"sqlite:///{sqlite_path_obj.resolve()}"

    return database_url


def _build_engine_options(database_url):
    if database_url.startswith('sqlite'):
        return {
            'pool_pre_ping': True,
            'connect_args': {
                'timeout': 30,
                'check_same_thread': False,
                'isolation_level': None,
            }
        }

    if database_url.startswith('postgresql'):
        return {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 20,
            'max_overflow': 40,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000',
            }
        }

    if database_url.startswith('mysql'):
        return {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 20,
            'max_overflow': 40,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'charset': 'utf8mb4',
            }
        }

    return {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }


class BaseConfig:
    BASE_DIR = BASE_DIR
    INSTANCE_DIR = INSTANCE_DIR
    DATA_DIR = DATA_DIR
    LOGS_DIR = LOGS_DIR
    CONFIG_DIR = CONFIG_DIR
    DEFAULT_DATABASE_URL = f'sqlite:///{INSTANCE_DIR / "app.db"}'
    DEBUG = False
    TESTING = False

    SECRET_KEY = ''
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_ENGINE_LOG_ENABLED = False

    DING_TALK_ACCESS_TOKEN = ''
    DING_TALK_SECRET = ''
    DING_TALK_DETAIL_BASE_URL = ''
    PUBLIC_BASE_URL = ''

    BASE_URL = 'http://localhost:5000'
    TASK_TIMEOUT = 3600
    LOG_LEVEL = 'INFO'
    LOG_FILE = LOGS_DIR / 'app.log'
    SQLALCHEMY_DATABASE_URI = DEFAULT_DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(SQLALCHEMY_DATABASE_URI)

    @classmethod
    def init_app(cls):
        cls.SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
        # 通过参数统一控制 SQLAlchemy SQL 输出。
        # 默认关闭，避免运行期被 SQL 日志刷屏；排查数据库问题时可显式设为 true。
        requested_sqlalchemy_echo = _get_bool('SQLALCHEMY_ECHO', False)
        cls.SQLALCHEMY_ENGINE_LOG_ENABLED = _get_bool(
            'SQLALCHEMY_ENGINE_LOG_ENABLED',
            False,
        )
        # 只要未显式开启 SQLAlchemy 引擎日志，就强制关闭 echo。
        # 这样即使环境里残留了 SQLALCHEMY_ECHO=True，重启后也不会继续刷 SQL。
        cls.SQLALCHEMY_ECHO = (
            requested_sqlalchemy_echo and cls.SQLALCHEMY_ENGINE_LOG_ENABLED
        )
        cls.DING_TALK_ACCESS_TOKEN = os.environ.get('DING_TALK_ACCESS_TOKEN', '')
        cls.DING_TALK_SECRET = os.environ.get('DING_TALK_SECRET', '')
        cls.DING_TALK_DETAIL_BASE_URL = os.environ.get(
            'DING_TALK_DETAIL_BASE_URL',
            '',
        )
        cls.PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '')
        cls.BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')
        cls.TASK_TIMEOUT = _get_int('TASK_TIMEOUT', 3600)
        cls.LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
        cls.LOG_FILE = cls.LOGS_DIR / 'app.log'
        cls.SQLALCHEMY_DATABASE_URI = _resolve_database_url(cls.DEFAULT_DATABASE_URL)
        cls.SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(cls.SQLALCHEMY_DATABASE_URI)

        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)
        if cls.SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
            cls.INSTANCE_DIR.mkdir(exist_ok=True)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    DEFAULT_DATABASE_URL = f'sqlite:///{INSTANCE_DIR / "app.db"}'


class ProductionConfig(BaseConfig):
    DEBUG = False
    DEFAULT_DATABASE_URL = 'postgresql://postgres:Hello12345*@172.18.20.17:5432/googlesheet_validator'


class TestingConfig(BaseConfig):
    TESTING = True
    DEFAULT_DATABASE_URL = f'sqlite:///{INSTANCE_DIR / "test.db"}'


CONFIG_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config_class():
    app_env = os.environ.get('APP_ENV', 'development').strip().lower() or 'development'
    return CONFIG_MAP.get(app_env, DevelopmentConfig)


Config = get_config_class()


def init_config():
    from app.models import SystemConfig
    from app.services.config_manager import get_config_manager

    config_manager = get_config_manager()

    default_configs = {
        'spreadsheet_id': {
            'value': '',
            'description': '默认 Google Spreadsheet ID，为空时需在任务或页面配置中指定。',
        },
        'sheet_name': {
            'value': 'data',
            'description': '默认工作表名称。',
        },
        'token_file': {
            'value': 'data/token.json',
            'description': '默认单 token 文件路径；启用 token 池后可被任务级 token_file 覆盖。',
        },
        'google_sheet_token_global_max_usage': {
            'value': 0,
            'description': 'Google token 全局总占用上限，0 表示不限制。',
        },
        'backtest_training_token_id': {
            'value': '',
            'description': 'Backtest training task token_id from google_sheet_tokens table.',
        },
        'proxy_url': {
            'value': None,
            'description': 'Google Sheet 请求默认代理地址，为空表示直连。',
        },
        'max_concurrent_tasks': {
            'value': 20,
            'description': '系统允许同时运行的任务总数上限。',
        },
        'task_timeout': {
            'value': 36000,
            'description': '单个任务执行超时时间，单位秒。',
        },
        'task_status_check_timeout': {
            'value': 600,
            'description': '任务状态检查超时时间，单位秒。',
        },
        'watchdog_enabled': {
            'value': True,
            'description': '是否启用任务看门狗线程。',
        },
        'watchdog_interval_seconds': {
            'value': 1800,
            'description': '看门狗巡检间隔，单位秒。',
        },
        'watchdog_log_timeout_minutes': {
            'value': 30,
            'description': '任务日志超过多少分钟未更新时，判定为可能卡死。',
        },
        'execution_delay_min': {
            'value': 20,
            'description': '批量执行时每步最小延迟，单位秒。',
        },
        'execution_delay_max': {
            'value': 30,
            'description': '批量执行时每步最大延迟，单位秒。',
        },
        'api_retry_max_attempts': {
            'value': 10,
            'description': '外部 API 最大重试次数。',
        },
        'api_retry_delay': {
            'value': 30,
            'description': '外部 API 重试间隔，单位秒。',
        },
        'frontend_polling_interval': {
            'value': 15000,
            'description': '前端任务轮询间隔，单位毫秒。',
        },
        'dashboard_refresh_interval': {
            'value': 30000,
            'description': '仪表盘自动刷新间隔，单位毫秒。',
        },
        'detail_refresh_interval': {
            'value': 60000,
            'description': '详情页自动刷新间隔，单位毫秒。',
        },
        'log_polling_interval': {
            'value': 3000,
            'description': '日志轮询间隔，单位毫秒。',
        },
        'log_realtime_interval': {
            'value': 3000,
            'description': '日志实时刷新间隔，单位毫秒。',
        },
        'tasks_admin_refresh_interval': {
            'value': 30000,
            'description': '管理页任务列表刷新间隔，单位毫秒。',
        },
        'parameter_positions': {
            'value': ['B6', 'B7', 'B9', 'B10', 'B11', 'B12'],
            'description': 'Google Sheet 主流程参数输入单元格位置列表。',
        },
        'check_positions': {
            'value': ['I6', 'I7', 'I9', 'I10', 'I11', 'I12'],
            'description': 'Google Sheet 主流程勾选/触发单元格位置列表。',
        },
        'result_positions': {
            'value': ['I15', 'I16', 'I17', 'I18', 'I19', 'I20', 'I21', 'I22', 'I23'],
            'description': 'Google Sheet 主流程结果读取单元格位置列表。',
        },

        "C3_commission_cell": {
            "value": "B5",
            "description": "C3 模板佣金单元格位置。",
        },

        'c3_parameter_positions': {
            'value': ['B5','B6', 'B7', 'B8','B9', 'B10', 'B11', 'B12'],
            'description': 'C3 模板参数输入单元格位置列表。',
        },
        'c3_check_positions': {
            'value': ["I15","I16"],
            'description': 'C3 模板勾选/触发单元格位置列表。',
        },
        'c3_input_column_d': {
            'value': 'D',
            'description': 'C3 模板输入列 D 的列标识。',
        },
        'c3_input_column_e': {
            'value': 'E',
            'description': 'C3 模板输入列 E 的列标识。',
        },
        'c3_output_range_1': {
            'value': 'I2:I23',
            'description': 'C3 模板第一段结果读取区域。',
        },
        'c3_output_range_2': {
            'value': 'I15:I23',
            'description': 'C3 模板第二段结果读取区域。',
        },
        'c3_output_column_K': {
            'value': 'K',
            'description': 'C3 模板输出列 K 的列标识。',
        },
        'c3_output_column_O': {
            'value': 'O',
            'description': 'C3 模板输出列 O 的列标识。',
        },


        'c4_input_column_a': {
            'value': 'A',
            'description': 'C4 模板输入列 A 的列标识。',
        },
        'c4_input_column_b': {
            'value': 'B',
            'description': 'C4 模板输入列 B 的列标识。',
        },
        'c4_output_range_1': {
            'value': 'D2:D20',
            'description': 'C4 模板第一段结果读取区域。',
        },
        'c4_output_range_2': {
            'value': 'D22:F25',
            'description': 'C4 模板第二段结果读取区域。',
        },
        'c4_output_column_j': {
            'value': 'J',
            'description': 'C4 模板输出列 J 的列标识。',
        },
        'c4_output_column_l': {
            'value': 'L',
            'description': 'C4 模板输出列 L 的列标识。',
        },

        'c5_parameter_positions': {
            'value': ['A1', 'B1'],
            'description': 'C5 模板参数输入单元格位置列表。',
        },
        'c5_check_positions': {
            'value': ['D2', 'D3'],
            'description': 'C5 模板勾选/触发单元格位置列表。',
        },
        'c5_input_column_a': {
            'value': 'A',
            'description': 'C5 模板输入列 A 的列标识。',
        },
        'c5_input_column_b': {
            'value': 'B',
            'description': 'C5 模板输入列 B 的列标识。',
        },
        'c5_output_range_1': {
            'value': 'D2:D20',
            'description': 'C5 模板第一段结果读取区域。',
        },
        'c5_output_range_2': {
            'value': 'D22:F25',
            'description': 'C5 模板第二段结果读取区域。',
        },
        'c5_output_column_j': {
            'value': 'J',
            'description': 'C5 模板输出列 J 的列标识。',
        },
        'c5_output_column_l': {
            'value': 'L',
            'description': 'C5 模板输出列 L 的列标识。',
        },
    }

    existing_configs = {
        row.key: row.description
        for row in SystemConfig.query.with_entities(SystemConfig.key, SystemConfig.description).all()
    }
    for key, item in default_configs.items():
        value = item['value']
        description = item['description']
        if key not in existing_configs:
            config_manager.set_config(key, value, description=description)
            print(f"初始化默认配置: {key}")
        elif not existing_configs.get(key):
            config_manager.set_config(key, config_manager.get_config(key, value), description=description)
            print(f"补充配置说明: {key}")


# RBAC 权限定义，格式：(group, code, name, route_path)
# route_path 仅供后台展示，标记该权限对应的前端路由入口
# run.py 启动时幂等插入到数据库
PERMISSIONS = [
    ('task',         'task:view',           '查看任务/日志/结果',    '/admin/tasks'),
    ('task',         'task:create',         '创建任务',              '/task/create'),
    ('task',         'task:cancel',         '取消任务',              None),
    ('task',         'task:restart',        '重启任务',              None),
    ('task',         'task:delete',         '删除任务',              None),
    ('template',     'template:view',       '查看模板',              '/admin/templates'),
    ('template',     'template:manage',     '管理模板',              '/admin/templates'),
    ('google_sheet', 'google_sheet:view',   '查看 Google Sheet',     '/admin/google-sheets'),
    ('google_sheet', 'google_sheet:manage', '管理 Google Sheet',     '/admin/google-sheets'),
    ('google_sheet', 'google_sheet:c3',     '访问 Google Sheet C3',  '/task/list?version=c3'),
    ('google_sheet', 'google_sheet:c4',     '访问 Google Sheet C4',  '/task/list?version=c4'),
    ('google_sheet', 'google_sheet:c5',     '访问 Google Sheet C5',  '/task/list?version=c5'),
    ('config',       'config:view',         '查看系统配置',          '/admin/config'),
    ('config',       'config:manage',       '修改系统配置',          '/admin/config'),
    ('scheduler',    'scheduler:view',      '查看定时任务',          '/admin/scheduler'),
    ('scheduler',    'scheduler:manage',    '管理定时任务',          '/admin/scheduler'),
    ('database',     'database:manage',     '数据库操作',            None),
    ('user',         'user:view',           '查看用户列表',          '/admin/users'),
    ('user',         'user:manage',         '管理用户/角色/权限',    '/admin/users'),
    ('backtest',     'backtest:view',       '查看回测任务',          '/backtest/list'),
    ('backtest',     'backtest:create',     '创建回测任务',          '/backtest/create'),
    ('page',         'page:admin:dashboard',    '访问仪表盘页面',         '/admin'),
    ('page',         'page:admin:tasks',        '访问任务管理页面',       '/admin/tasks'),
    ('page',         'page:admin:templates',    '访问任务模板页面',       '/admin/templates'),
    ('page',         'page:admin:results',      '访问任务结果页面',       '/admin/results'),
    ('page',         'page:admin:scheduler',    '访问定时任务页面',       '/admin/scheduler'),
    ('page',         'page:admin:config',       '访问系统配置页面',       '/admin/config'),
    ('page',         'page:admin:google_sheets','访问 Google Sheet 管理页面', '/admin/google-sheets'),
    ('page',         'page:admin:logs',         '访问系统日志页面',       '/admin/logs'),
    ('page',         'page:admin:users',        '访问用户管理页面',       '/admin/users'),
    ('page',         'page:admin:roles',        '访问角色管理页面',       '/admin/roles'),
    ('page',         'page:google_sheet:c3',    '访问 Google Sheet C3 页面', '/google-sheet/?version=c3'),
    ('page',         'page:google_sheet:c4',    '访问 Google Sheet C4 页面', '/google-sheet/?version=c4'),
    ('page',         'page:google_sheet:c5',    '访问 Google Sheet C5 页面', '/google-sheet/?version=c5'),
    ('page',         'page:backtest:list',      '访问回测列表页面',       '/backtest-training/list'),
    ('page',         'page:backtest:create',    '访问回测创建页面',       '/backtest-training/create'),
]

# 导航菜单默认结构，存入 system_configs.nav_menu
# 每个菜单项的 permission 字段对应 PERMISSIONS 中的 code
# 无 permission 字段表示登录即可访问
NAV_MENU = [
    {"key": "dashboard", "label": "仪表盘", "path": "/admin", "permission": "page:admin:dashboard"},
    {"key": "task", "label": "任务模块", "children": [
        {"key": "tasks",     "label": "任务管理", "path": "/admin/tasks",     "permission": "page:admin:tasks"},
        {"key": "templates", "label": "任务模板", "path": "/admin/templates", "permission": "page:admin:templates"},
        {"key": "results",   "label": "任务结果", "path": "/admin/results",   "permission": "page:admin:results"},
    ]},
    {"key": "scheduler_group", "label": "调度模块", "children": [
        {"key": "scheduler", "label": "定时任务", "path": "/admin/scheduler", "permission": "page:admin:scheduler"},
    ]},
    {"key": "system", "label": "系统模块", "children": [
        {"key": "config",   "label": "系统配置",          "path": "/admin/config",        "permission": "page:admin:config"},
        {"key": "sheets",   "label": "Google Sheet 管理", "path": "/admin/google-sheets", "permission": "page:admin:google_sheets"},
        {"key": "logs",     "label": "系统日志",          "path": "/admin/logs",          "permission": "page:admin:logs"},
        {"key": "users",    "label": "用户管理",          "path": "/admin/users",         "permission": "page:admin:users"},
        {"key": "roles",    "label": "角色管理",          "path": "/admin/roles",         "permission": "page:admin:roles"},
    ]},
    {"key": "business", "label": "业务模块", "children": [
        {"key": "c3",      "label": "Google Sheet C3", "path": "/task/list?version=c3", "permission": "page:google_sheet:c3"},
        {"key": "c4",      "label": "Google Sheet C4", "path": "/task/list?version=c4", "permission": "page:google_sheet:c4"},
        {"key": "c5",      "label": "Google Sheet C5", "path": "/task/list?version=c5", "permission": "page:google_sheet:c5"},
        {"key": "backtest","label": "数据回测",         "path": "/backtest/list",        "permission": "page:backtest:list"},
        {"key": "xpl",     "label": "夏普率计算",       "path": "/xpl"},
        {"key": "xpl_v1",  "label": "V1 回测数据分析",  "path": "/xpl/v1"},
    ]},
]
