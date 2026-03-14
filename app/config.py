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
    return os.environ.get('DATABASE_URL') or default_url


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

    DING_TALK_ACCESS_TOKEN = ''
    DING_TALK_SECRET = ''

    BASE_URL = 'http://localhost:5000'
    TASK_TIMEOUT = 3600
    LOG_LEVEL = 'INFO'
    LOG_FILE = LOGS_DIR / 'app.log'
    SQLALCHEMY_DATABASE_URI = DEFAULT_DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(SQLALCHEMY_DATABASE_URI)

    @classmethod
    def init_app(cls):
        cls.SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
        cls.SQLALCHEMY_ECHO = _get_bool('SQLALCHEMY_ECHO', False)
        cls.DING_TALK_ACCESS_TOKEN = os.environ.get('DING_TALK_ACCESS_TOKEN', '')
        cls.DING_TALK_SECRET = os.environ.get('DING_TALK_SECRET', '')
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
        'spreadsheet_id': '',
        'sheet_name': 'data',
        'token_file': 'data/token.json',
        'google_sheet_token_global_max_usage': 0,
        'proxy_url': None,
        'max_concurrent_tasks': 20,
        'task_timeout': 36000,
        'task_status_check_timeout': 600,
        'watchdog_enabled': True,
        'watchdog_interval_seconds': 1800,
        'watchdog_log_timeout_minutes': 30,
        'execution_delay_min': 20,
        'execution_delay_max': 30,
        'api_retry_max_attempts': 10,
        'api_retry_delay': 30,
        'frontend_polling_interval': 15000,
        'dashboard_refresh_interval': 30000,
        'detail_refresh_interval': 60000,
        'log_polling_interval': 3000,
        'log_realtime_interval': 3000,
        'tasks_admin_refresh_interval': 30000,
        'parameter_positions': ['B6', 'B7', 'B9', 'B10', 'B11', 'B12'],
        'check_positions': ['I6', 'I7', 'I9', 'I10', 'I11', 'I12'],
        'result_positions': ['I15', 'I16', 'I17', 'I18', 'I19', 'I20', 'I21', 'I22', 'I23'],
        'c4_input_column_a': 'A',
        'c4_input_column_b': 'B',
        'c4_output_range_1': 'D2:D20',
        'c4_output_range_2': 'D22:F25',
        'c4_output_column_j': 'J',
        'c4_output_column_l': 'L',
        'c5_parameter_positions': ['A1', 'B1'],
        'c5_check_positions': ['G1', 'H1'],
        'c5_input_column_a': 'A',
        'c5_input_column_b': 'B',
        'c5_output_range_1': 'D2:D20',
        'c5_output_range_2': 'D22:F25',
        'c5_output_column_j': 'J',
        'c5_output_column_l': 'L',
    }

    existing_keys = {c.key for c in SystemConfig.query.with_entities(SystemConfig.key).all()}
    for key, value in default_configs.items():
        if key not in existing_keys:
            config_manager.set_config(key, value)
            print(f"初始化默认配置: {key}")
