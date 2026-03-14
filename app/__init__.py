import os
from pathlib import Path

from flask import Flask
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

from app.extensions import db, migrate
from app.routes import register_blueprints
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

    db.init_app(app)
    migrate.init_app(app, db)

    from app.services.config_manager import get_config_manager
    get_config_manager().init_app(app)

    register_blueprints(app)

    app.notifier = DingTalkNotifier(
        access_token=app.config.get('DING_TALK_ACCESS_TOKEN', ''),
        secret=app.config.get('DING_TALK_SECRET', ''),
    )

    return app
