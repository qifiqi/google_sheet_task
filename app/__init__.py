import os
import logging
from pathlib import Path

from flask import Flask, abort, g, jsonify, request

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        """在未安装 dotenv 的环境中保持应用可启动。"""
        return False

from app.extensions import db, migrate
from app.routes import register_blueprints
from app.utils.auth import authenticate_current_request, is_retired_local_identity_path, validate_auth_runtime_settings
from app.utils.ding_talk_notifier import DingTalkNotifier


def load_app_environment():
    """按基础环境和当前运行环境的顺序加载配置文件。"""
    project_root = Path(__file__).parent.parent

    base_env = project_root / '.env'
    if base_env.exists():
        load_dotenv(base_env, override=False)

    app_env = os.environ.get('APP_ENV', 'development').strip().lower() or 'development'
    scoped_env = project_root / f'.env.{app_env}'
    if scoped_env.exists():
        load_dotenv(scoped_env, override=False)


def create_app():
    """创建并配置 Flask 应用、扩展、认证网关和全部业务蓝图。"""
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

    @app.before_request
    def require_gateway_jwt():
        """按开关启用保留的主 Web JWT 网关；默认使用本地登录与 RBAC。"""
        if not app.config.get('REMOTE_IDENTITY_GATEWAY_ENABLED', False):
            return None
        if request.path.startswith('/static/') or request.path == '/login':
            return None
        if is_retired_local_identity_path(request.path):
            abort(404)
        if request.path in {'/api/auth/login', '/api/auth/refresh'}:
            return None
        auth_error = authenticate_current_request()
        if auth_error:
            return auth_error
        if (
            app.config.get('REMOTE_MODEL_ACCESS_ENFORCED')
            and request.method == 'GET'
            and not request.path.startswith('/api/')
        ):
            model_codes = getattr(g, 'current_model_codes', None)
            if model_codes is None:
                return jsonify({'code': 503, 'data': None, 'message': 'JWT 未携带主 Web 模型权限'}), 503
            from app.repositories.sys_model_repository import SysModelRepository
            from app.services.menu_service import MenuService
            from app.services.model_access_service import is_path_allowed
            from werkzeug.exceptions import NotFound

            def is_local_route(link):
                """验证远程菜单链接是否对应本应用已注册的 GET 路由。"""
                try:
                    app.url_map.bind('').match(link.split('?', 1)[0], method='GET')
                    return True
                except NotFound:
                    return False

            menu = MenuService(SysModelRepository()).get_menu(
                cache_key=str(g.current_user.id), is_available=is_local_route,
            )
            current_path = request.full_path.rstrip('?')
            if not is_path_allowed(menu, model_codes, current_path):
                return jsonify({'code': 403, 'data': None, 'message': '无该模型访问权限'}), 403
        return None

    @app.context_processor
    def inject_template_auth_context():
        """向所有模板暴露认证开关，供前端选择登录态交互。"""
        return {
            'auth_enabled': os.environ.get('AUTH_ENABLED', 'true').lower() == 'true',
        }

    app.notifier = DingTalkNotifier(
        access_token=app.config.get('DING_TALK_ACCESS_TOKEN', ''),
        secret=app.config.get('DING_TALK_SECRET', ''),
    )

    return app
