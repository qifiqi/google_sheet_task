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
DATA_DIR = BASE_DIR / 'data'          # token、导入文件等运行时数据。
LOGS_DIR = BASE_DIR / 'logs'          # 应用日志目录。


def _resolve_database_url():
    # SQLite 本地回退已移除：DATABASE_URL 必须显式配置（MySQL/PostgreSQL）。
    return os.environ.get('DATABASE_URL', '')


def _build_engine_options(_database_url):
    options = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': _get_int('DB_POOL_SIZE', 10),
        'max_overflow': _get_int('DB_MAX_OVERFLOW', 20),
        'pool_timeout': _get_int('DB_POOL_TIMEOUT', 30),
    }
    # MySQL 显式声明 utf8mb4，避免跟随服务端/握手默认造成的中文乱码风险。
    if _database_url.startswith('mysql'):
        options['connect_args'] = {'charset': 'utf8mb4'}
    return options


class BaseConfig:
    # Flask 从该配置类读取最终配置；环境文件已在 app.create_app() 中先加载。
    BASE_DIR = BASE_DIR
    DATA_DIR = DATA_DIR
    LOGS_DIR = LOGS_DIR
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
    # 股票服务基地址；K线 SDK / 参数回推(StockAPIClient) / 代理池(SmartProxyManager) 共用，
    # 为空时各消费方回退自身历史默认地址。
    STOCK_BASE_URL = ''
    # 外部 Token 校验（stock_sdk SysUser/GetUserInfo）：非本站 JWT 的请求令牌
    # 经该接口校验通过后放行本站接口；为空时关闭该回落通道。
    STOCK_AUTH_BASE_URL = 'http://172.18.20.20:7070'
    STOCK_AUTH_TIMEOUT = 5
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
    # 最终数据库地址由 init_app() 根据 DATABASE_URL 解析；未配置时启动期直接报错。
    SQLALCHEMY_DATABASE_URI = ''
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options('')

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
        # 股票服务基地址，单一来源：环境变量 STOCK_BASE_URL。
        # 三个消费方共用：K线 SDK(StockClient/KlineService)、参数回推(StockAPIClient)、
        # 代理池(SmartProxyManager)。未配置时保持空串，各消费方回退自身历史默认地址。
        cls.STOCK_BASE_URL = os.environ.get('STOCK_BASE_URL', '')
        cls.STOCK_AUTH_BASE_URL = os.environ.get(
            'STOCK_AUTH_BASE_URL',
            'http://172.18.20.20:7070',
        )
        cls.STOCK_AUTH_TIMEOUT = _get_int('STOCK_AUTH_TIMEOUT', 5)
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
        cls.SQLALCHEMY_DATABASE_URI = _resolve_database_url()
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError(
                'DATABASE_URL 未配置：SQLite 本地回退已移除，'
                '必须在环境文件中显式设置数据库连接串（MySQL/PostgreSQL）'
            )
        cls.SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(cls.SQLALCHEMY_DATABASE_URI)

        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)


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
    from app.seeds.system_config_seeds import build_default_configs

    config_manager = get_config_manager()

    default_configs = build_default_configs()

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


