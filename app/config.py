import os
import secrets
from pathlib import Path


def _get_bool(name, default=False):
    """读取布尔环境变量；支持 true/1/yes/on（不区分大小写）。"""
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes', 'on')


def _get_int(name, default):
    """读取整数环境变量；变量存在但不是整数时会在启动阶段报错。"""
    return int(os.environ.get(name, default))


# 项目根目录及运行时数据目录。路径配置不是从 .env 读取的，统一相对于项目根目录。
BASE_DIR = Path(__file__).parent.parent
INSTANCE_DIR = BASE_DIR / 'instance'  # SQLite 数据库目录。
DATA_DIR = BASE_DIR / 'data'          # token、导入文件等运行时数据。
LOGS_DIR = BASE_DIR / 'logs'          # 应用日志目录。
CONFIG_DIR = BASE_DIR / 'config'      # 预留的配置文件目录。


def _resolve_database_url(default_url):
    database_url = os.environ.get('DATABASE_URL') or default_url

    if database_url.startswith('sqlite:///'):
        sqlite_path = database_url.replace('sqlite:///', '', 1)
        sqlite_path_obj = Path(sqlite_path)
        if not sqlite_path_obj.is_absolute():
            sqlite_path_obj = BASE_DIR / sqlite_path_obj
        database_url = f"sqlite:///{sqlite_path_obj.resolve().as_posix()}"

    return database_url


def _build_engine_options(_database_url):
    options = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }
    # 池容量参数对非 SQLite 引擎生效（MySQL 主力 + PostgreSQL 历史在用同享）；
    # SQLite 仅本地回退，走默认池化。
    if not _database_url.startswith('sqlite'):
        options.update({
            'pool_size': _get_int('DB_POOL_SIZE', 10),
            'max_overflow': _get_int('DB_MAX_OVERFLOW', 20),
            'pool_timeout': _get_int('DB_POOL_TIMEOUT', 30),
        })
    # MySQL 显式声明 utf8mb4，避免跟随服务端/握手默认造成的中文乱码风险。
    if _database_url.startswith('mysql'):
        options['connect_args'] = {'charset': 'utf8mb4'}
    return options


class BaseConfig:
    # Flask 从该配置类读取最终配置；环境文件已在 app.create_app() 中先加载。
    BASE_DIR = BASE_DIR
    INSTANCE_DIR = INSTANCE_DIR
    DATA_DIR = DATA_DIR
    LOGS_DIR = LOGS_DIR
    CONFIG_DIR = CONFIG_DIR
    # 未设置 DATABASE_URL 时使用 instance/app.db，适合最小本地运行。
    DEFAULT_DATABASE_URL = f'sqlite:///{INSTANCE_DIR / "app.db"}'
    DEBUG = False
    TESTING = False

    # Flask session 等签名密钥；init_app() 会从 SECRET_KEY 环境变量读取，
    # 未配置时生成随机值（重启后会变化，不适合生产环境）。
    SECRET_KEY = ''
    # 当前项目固定关闭 SQLAlchemy 修改追踪；不要通过 .env 中同名变量修改。
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 是否输出 SQL 语句；必须同时打开 SQLALCHEMY_ENGINE_LOG_ENABLED 才会生效。
    SQLALCHEMY_ECHO = False
    # 是否启用 sqlalchemy.engine 日志，默认关闭以避免日志刷屏。
    SQLALCHEMY_ENGINE_LOG_ENABLED = False
    # 请求体/上传上限：import-excel 上传 Excel 的合理上限（超限 Flask 抛 413
    # → errors.py HTTPException 链自动转信封）。见 api-model-query-audit/07 §2.2。
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    # 钉钉通知凭据和详情链接；为空时不发送对应通知或使用默认行为。
    DING_TALK_ACCESS_TOKEN = ''
    DING_TALK_SECRET = ''
    DING_TALK_DETAIL_BASE_URL = ''
    # 对外展示的应用地址，例如反向代理后的 https://example.com。
    PUBLIC_BASE_URL = ''

    # Flask/前端使用的应用基础地址。
    BASE_URL = 'http://localhost:5000'
    # 股票 SDK / K 线服务地址；为空时由 SDK 使用默认地址。
    STOCK_BASE_URL = ''
    # 主服务 SSO（docs/design/sso-integration-2026-09/）：主服务侧边栏携带 Token
    # 跳入 /login#sso_token=...，子服务回调主服务校验接口换发本地 JWT。
    SSO_ENABLED = True
    SSO_MAIN_VERIFY_URL = 'https://stockapi.stplan.cn/api/SysUser/GetUserInfo'
    # 校验接口超时（秒）；换票是低频入口操作，短超时快速失败。
    SSO_MAIN_VERIFY_TIMEOUT = 5
    # 单个任务最长执行时间，单位：秒。
    TASK_TIMEOUT = 3600
    # 应用日志级别；LOG_FILE 固定写入 logs/app.log。
    LOG_LEVEL = 'INFO'
    LOG_FILE = LOGS_DIR / 'app.log'
    # 最终数据库地址由 init_app() 根据 DATABASE_URL 解析。
    SQLALCHEMY_DATABASE_URI = DEFAULT_DATABASE_URL
    # 数据库连接池参数，SQLite 不使用 pool_size/max_overflow 等参数。
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
        # 股票 SDK(StockClient/KlineService) 的服务地址，单一来源：环境变量 STOCK_BASE_URL。
        # 未配置时保持空串，由 stock_sdk 使用其默认地址。
        cls.STOCK_BASE_URL = os.environ.get('STOCK_BASE_URL', '')
        # 主服务 SSO 配置：环境变量可覆盖默认值（多环境部署指向不同主服务）。
        cls.SSO_ENABLED = _get_bool('SSO_ENABLED', True)
        cls.SSO_MAIN_VERIFY_URL = os.environ.get(
            'SSO_MAIN_VERIFY_URL',
            'https://stockapi.stplan.cn/api/SysUser/GetUserInfo',
        )
        cls.SSO_MAIN_VERIFY_TIMEOUT = _get_int('SSO_MAIN_VERIFY_TIMEOUT', 5)
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


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    RATELIMIT_ENABLED = False


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
        'google_sheet_http_timeout': {
            'value': 30,
            'description': 'Google Sheet 请求默认 HTTP 超时，单位秒。',
        },
        'backtest_training_token_id': {
            'value': '',
            'description': 'Backtest training task token_id from google_sheet_tokens table.',
        },
        'proxy_url': {
            'value': None,
            'description': 'Google Sheet 请求默认代理地址，为空表示直连。',
        },
        'dfcf_kline_proxy_enabled': {
            'value': False,
            'description': '是否为东方财富 K 线接口启用 proxy_manager 代理。true 启用，false 直连。',
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
        'rate_limit_analyze': {
            'value': 10,
            'description': '绩效分析接口限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_heavy': {
            'value': 6,
            'description': '重计算端点（Excel 导入/比例计算）限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_rebuild': {
            'value': 2,
            'description': '模型汇总重建端点限流：每分钟每用户次数（0=不限）。',
        },
        'rate_limit_export': {
            'value': 10,
            'description': '导出端点限流：每分钟每用户次数（0=不限）。',
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
            'value': ['G1', 'H1'],
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

        'c7_parameter_positions': {
            'value': ['A1', 'B1'],
            'description': 'C5 模板参数输入单元格位置列表。',
        },
        'c7_check_positions': {
            'value': ['G1', 'H1'],
            'description': 'C5 模板勾选/触发单元格位置列表。',
        },
        'c7_input_column_a': {
            'value': 'A',
            'description': 'C5 模板输入列 A 的列标识。',
        },
        'c7_input_column_b': {
            'value': 'B',
            'description': 'C5 模板输入列 B 的列标识。',
        },
        'c7_0_3_kline_start_row': {
            'value': 2,
            'description': 'C7.0.3 OHLC K线输入起始行。',
        },
        'c7_0_3_kline_date_column': {
            'value': 'CC',
            'description': 'C7.0.3 OHLC K线日期列。',
        },
        'c7_0_3_kline_open_column': {
            'value': 'CD',
            'description': 'C7.0.3 OHLC K线开盘价列。',
        },
        'c7_0_3_kline_high_column': {
            'value': 'CE',
            'description': 'C7.0.3 OHLC K线最高价列。',
        },
        'c7_0_3_kline_low_column': {
            'value': 'CF',
            'description': 'C7.0.3 OHLC K线最低价列。',
        },
        'c7_0_3_kline_close_column': {
            'value': 'CG',
            'description': 'C7.0.3 OHLC K线收盘价列。',
        },
        'c7_0_3_output_range_1': {
            'value': 'D2:D20',
            'description': 'C7.0.3 第一段结果读取区域，与 C5 一致。',
        },
        'c7_0_3_output_range_2': {
            'value': 'D22:F25',
            'description': 'C7.0.3 第二段结果读取区域，与 C5 一致。',
        },
        'c7_0_3_output_column_j': {
            'value': 'J',
            'description': 'C7.0.3 指数收益输出列，与 C5 一致。',
        },
        'c7_0_3_output_column_l': {
            'value': 'L',
            'description': 'C7.0.3 起始收益输出列，与 C5 一致。',
        },
        # 'c7_output_range_1': {
        #     'value': 'D2:F4',
        #     'description': 'C5 模板第一段结果读取区域。',
        # },
        'c7_output_range_1': {
            'value': 'D8:D26',
            'description': 'C5 模板第一段结果读取区域。',
        },
        'c7_output_range_2': {
            'value': 'D28:F31',
            'description': 'C5 模板第二段结果读取区域。',
        },
        'c7_output_column_j': {
            'value': 'J',
            'description': 'C5 模板输出列 J 的列标识。',
        },
        'c7_output_column_l': {
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
# 仅保留页面权限（page:*），接口级细粒度权限已移除；
# 页面权限同时由导航菜单表通过 sync_navigation_permissions 幂等同步。
PERMISSIONS = [
    ('page',         'page:admin:dashboard',    '访问仪表盘页面',         '/admin'),
    ('page',         'page:admin:tasks',        '访问任务管理页面',       '/admin/tasks'),
    ('page',         'page:admin:templates',    '访问任务模板页面',       '/admin/templates'),
    ('page',         'page:admin:results',      '访问任务结果页面',       '/admin/results'),
    ('page',         'page:admin:model_summary','访问单模型汇总页面',     '/admin/model-summary'),
    ('page',         'page:admin:scheduler',    '访问定时任务页面',       '/admin/scheduler'),
    ('page',         'page:admin:config',       '访问系统配置页面',       '/admin/config'),
    ('page',         'page:admin:navigation',   '访问路由表页面',         '/admin/navigation'),
    ('page',         'page:admin:google_sheets','访问 Google Sheet 管理页面', '/admin/google-sheets'),
    ('page',         'page:admin:logs',         '访问系统日志页面',       '/admin/logs'),
    ('page',         'page:admin:users',        '访问用户管理页面',       '/admin/users'),
    ('page',         'page:admin:roles',        '访问角色管理页面',       '/admin/roles'),
    ('page',         'page:google_sheet:c3',    '访问 Google Sheet C3 页面', '/google-sheet/?version=c3'),
    ('page',         'page:google_sheet:c4',    '访问 Google Sheet C4 页面', '/google-sheet/?version=c4'),
    ('page',         'page:google_sheet:c5',    '访问 Google Sheet C5 页面', '/google-sheet/?version=c5'),
    ('page',         'page:google_sheet:c7',    '访问 Google Sheet C7 页面', '/google-sheet/?version=c7'),
    ('page',         'page:backtest:list',      '访问回测列表页面',       '/backtest-training/list'),
    ('page',         'page:backtest:create',    '访问回测创建页面',       '/backtest-training/create'),
    ('page',         'page:backtest_multi_product:list',   '访问多品数据回测列表页面',   '/backtest-multi-product/list'),
    ('page',         'page:backtest_multi_product:create', '访问多品数据回测创建页面',   '/backtest-multi-product/create'),
    ('page',         'page:global_preview:single_product', '访问单品全局预览页面', '/global-preview/single_product'),
]

# 主服务 SSO 默认角色（docs/design/sso-integration-2026-09/）。
# init_rbac 幂等播种角色；权限按并集补齐，不覆盖管理员后台的手工调整。
SSO_ROLE = {
    'code': 'main_service_user',
    'name': '主服务用户',
    'description': '主服务 SSO 登录默认角色：仪表盘 + 数据/业务模块初始路由',
}
# 默认权限 = 仪表盘（登录落地页）+ DEFAULT_NAVIGATION_MENU 数据/业务模块初始路由；
# 东方财富 K 线、夏普率、回测数据分析的导航项无 page:* 权限码，天然对全部登录用户可见。
SSO_DEFAULT_PERMISSION_CODES = (
    'page:admin:dashboard',
    'page:admin:model_summary',
    'page:global_preview:single_product',
    'page:google_sheet:c3',
    'page:google_sheet:c4',
    'page:google_sheet:c5',
    'page:google_sheet:c7',
    'page:backtest:list',
    'page:backtest_multi_product:list',
)

