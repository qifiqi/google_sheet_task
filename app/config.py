import os
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        print("WARNING: Using generated SECRET_KEY. Set SECRET_KEY environment variable in production!")
    
    # 数据库配置
    # 使用instance文件夹存储数据库文件
    BASE_DIR = Path(__file__).parent.parent
    INSTANCE_DIR = BASE_DIR / 'instance'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{INSTANCE_DIR}/app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', 'False').lower() == 'true'  # SQL调试模式
    
    dd_access_token='a0fe95aac4a01a4c6826caf95087698baa6473804ee81dc2afaf4458e770eccc'
    dd_secret='SEC3309a1318e963385c7a805d2530cb7d6f2128fe4c9f26673cbad7f599927a498'

    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

    database_url = os.environ.get('DATABASE_URL') or f'sqlite:///{INSTANCE_DIR}/app.db'

    if database_url.startswith('sqlite'):
        # SQLite 特定配置 - 优化并发性能
        SQLALCHEMY_ENGINE_OPTIONS =  {
            'pool_pre_ping': True,  # 连接前ping，确保连接有效
            'connect_args': {
                'timeout': 30,  # SQLite锁超时时间（秒）
                'check_same_thread': False,  # 允许多线程访问
                'isolation_level': None,  # 自动提交模式，提升性能
            }
        }
    elif database_url.startswith('postgresql'):
        # PostgreSQL 配置 - 高性能优化
        SQLALCHEMY_ENGINE_OPTIONS =  {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 20,  # PostgreSQL 可以支持更大的连接池
            'max_overflow': 40,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000',  # 30秒查询超时
            }
        }
    elif database_url.startswith('mysql'):
        # MySQL 配置
        SQLALCHEMY_ENGINE_OPTIONS =  {
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
    else:
        # 通用数据库配置
        SQLALCHEMY_ENGINE_OPTIONS =  {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 10,
            'max_overflow': 20,
            'pool_timeout': 30,
        }

    # 文件路径配置
    DATA_DIR = BASE_DIR / 'data'
    LOGS_DIR = BASE_DIR / 'logs'
    CONFIG_DIR = BASE_DIR / 'config'
    
    # 确保目录存在
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    # 只有SQLite需要instance目录
    if database_url.startswith('sqlite'):
        INSTANCE_DIR.mkdir(exist_ok=True)
    # CONFIG_DIR.mkdir(exist_ok=True)
    
    # 任务配置
    MAX_CONCURRENT_TASKS = int(os.environ.get('MAX_CONCURRENT_TASKS', 5))
    TASK_TIMEOUT = int(os.environ.get('TASK_TIMEOUT', 3600))  # 1小时
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = LOGS_DIR / 'app.log'
    

def init_config():
    from app.services.config_manager import get_config_manager
    from app.models import SystemConfig
    
    config_manager = get_config_manager()
    
    # 默认配置 - 只在配置不存在时设置
    default_configs = {
        'spreadsheet_id': '',
        'sheet_name': 'data',
        'token_file': 'data/token.json',
        'proxy_url': None,
        'max_concurrent_tasks': 5,
        'task_timeout': 36000,
        'task_status_check_timeout': 600,  # 10分钟，任务状态检查超时
        'watchdog_enabled': True,
        'watchdog_interval_seconds': 1800,
        'watchdog_log_timeout_minutes': 30, # 30分钟 日志超时时间
        'execution_delay_min': 20,  # 执行延迟最小值（秒）
        'execution_delay_max': 30,  # 执行延迟最大值（秒）
        'api_retry_max_attempts': 10,  # API重试最大次数
        'api_retry_delay': 30,  # API重试延迟（秒）
        'frontend_polling_interval': 15000,  # 前端轮询间隔（毫秒）
        'dashboard_refresh_interval': 30000,  # 仪表板刷新间隔（毫秒）
        'detail_refresh_interval': 60000,  # 详情页刷新间隔（毫秒）
        'log_polling_interval': 3000,  # 日志轮询间隔（毫秒）
        'log_realtime_interval': 3000,  # 日志实时更新间隔（毫秒）
        'tasks_admin_refresh_interval': 30000,  # 管理页面任务刷新间隔（毫秒）
        'parameter_positions': [
            'B6',
            'B7',
            'B9',
            'B10',
            'B11',
            'B12'
        ],
        'check_positions': [
            'I6',
            'I7',
            'I9',
            'I10',
            'I11',
            'I12'
        ],
        'result_positions': [
            'I15',
            'I16',
            'I17',
            'I18',
            'I19',
            'I20',
            'I21',
            'I22',
            'I23',
        ],
        'c4_input_column_a': 'A',
        'c4_input_column_b': 'B',
        'c4_output_range_1': 'D2:D20',
        'c4_output_range_2': 'D22:F25',
        'c4_output_column_j': 'J',
        'c4_output_column_l': 'L',

        'c5_parameter_positions': [
            'A1',
            'B1'
        ],
        'c5_check_positions': [
            'G1',
            'H1',
        ],
        'c5_input_column_a': 'A',
        'c5_input_column_b': 'B',
        'c5_output_range_1': 'D2:D20',
        'c5_output_range_2': 'D22:F25',
        'c5_output_column_j': 'J',
        'c5_output_column_l': 'L',
    }
    
    # 只设置不存在的配置项，避免覆盖用户修改的配置
    existing_keys = {c.key for c in SystemConfig.query.with_entities(SystemConfig.key).all()}
    for key, value in default_configs.items():
        if key not in existing_keys:
            config_manager.set_config(key, value)
            print(f"初始化默认配置: {key}")
        # else:
        #     print(f"配置已存在，跳过: {key}")