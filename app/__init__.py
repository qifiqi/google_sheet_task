import os
import logging
from pathlib import Path

from flask import Flask

try:
    from dotenv import dotenv_values
except ImportError:
    def dotenv_values(*_args, **_kwargs):
        return {}

from app.extensions import db, limiter, migrate
from app.routes import register_blueprints
from app.utils.auth import validate_auth_runtime_settings
from app.utils.ding_talk_notifier import DingTalkNotifier


def load_app_environment():
    """加载环境文件，优先级为：真实环境变量 > 环境专属文件 > 基础 .env。

    先保存启动进程已有的环境变量，避免环境文件覆盖 VSCode launch.json、
    Docker environment 或系统环境中的显式配置。
    """
    project_root = Path(__file__).parent.parent
    process_env = dict(os.environ)

    base_env = project_root / '.env'
    base_values = dotenv_values(base_env) if base_env.exists() else {}

    # APP_ENV 需要先确定，才能选择 .env.development 等环境专属文件。
    app_env = (
        process_env.get('APP_ENV')
        or base_values.get('APP_ENV')
        or 'development'
    ).strip().lower() or 'development'
    scoped_env = project_root / f'.env.{app_env}'
    scoped_values = dotenv_values(scoped_env) if scoped_env.exists() else {}

    # 先写环境专属文件，再写基础文件；后者只补充尚未设置的键。
    # process_env 中的键永远不改，因此真实环境变量优先级最高。
    for values in (scoped_values, base_values):
        for key, value in values.items():
            if value is not None and key not in process_env and key not in os.environ:
                os.environ[key] = value

    os.environ.setdefault('APP_ENV', app_env)


def create_app():
    load_app_environment()
    validate_auth_runtime_settings()

    from app.config import get_config_class

    current_dir = Path(__file__).parent.parent
    template_dir = current_dir / 'templates'
    static_dir = current_dir / 'static'

    config_class = get_config_class()
    config_class.init_app()

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config.from_object(config_class)

    # 默认关闭 sqlalchemy.engine 的 SQL 语句日志，避免运行期日志被大量 SQL 输出淹没。
    # 如需排查数据库问题，可通过 SQLALCHEMY_ENGINE_LOG_ENABLED=true 临时打开。
    sqlalchemy_engine_logger = logging.getLogger("sqlalchemy.engine")
    sqlalchemy_engine_logger.disabled = not app.config.get(
        "SQLALCHEMY_ENGINE_LOG_ENABLED",
        False,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from app.errors import register_error_handlers
    register_error_handlers(app)

    from app.services.config_manager import get_config_manager
    get_config_manager().init_app(app)

    register_blueprints(app)

    @app.context_processor
    def inject_template_auth_context():
        return {
            'auth_enabled': os.environ.get('AUTH_ENABLED', 'true').lower() == 'true',
        }

    app.notifier = DingTalkNotifier(
        access_token=app.config.get('DING_TALK_ACCESS_TOKEN', ''),
        secret=app.config.get('DING_TALK_SECRET', ''),
    )

    return app
