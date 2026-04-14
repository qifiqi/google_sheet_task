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
