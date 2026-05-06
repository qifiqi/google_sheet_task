import os
import logging
from pathlib import Path

from flask import Flask
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

from app.extensions import db, migrate
from app.routes import register_blueprints
from app.utils.auth import validate_auth_runtime_settings
from app.utils.ding_talk_notifier import DingTalkNotifier


def load_app_environment():
    project_root = Path(__file__).parent.parent

    base_env = project_root / '.env'
    if base_env.exists():
        load_dotenv(base_env, override=False)

    app_env = os.environ.get('APP_ENV', 'development').strip().lower() or 'development'
    scoped_env = project_root / f'.env.{app_env}'
    if scoped_env.exists():
        load_dotenv(scoped_env, override=False)


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
