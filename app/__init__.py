import logging
from pathlib import Path

from flask import Flask

from app.env_loader import load_app_environment

# 数据层在 import 期按 DATA_ACCESS_MODE 绑定（app/repositories/__init__.py），
# 必须在本模块导入 routes/services 之前加载 .env，否则本地 db 模式不生效。
load_app_environment()

from app.extensions import db, limiter, migrate


def create_app():
    # 路由/鉴权/通知器延迟到 env 加载后导入，确保仓储按正确的 DATA_ACCESS_MODE 绑定。
    from app.routes import register_blueprints
    from app.utils.auth import get_app_env, is_auth_enabled
    from app.utils.ding_talk_notifier import DingTalkNotifier

    # 本地 JWT 密钥/认证开关校验已随本地登录一并停用（单 Token 子服务
    # 模式不使用本地 JWT_SECRET_KEY）；恢复本地登录时一并取消注释。
    # validate_auth_runtime_settings()

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

    # jsonify / request.get_json 统一走 orjson（见 app/utils/json_utils.py）。
    from app.utils.json_utils import OrjsonJSONProvider
    app.json = OrjsonJSONProvider(app)

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

    if not is_auth_enabled() and get_app_env() not in ("development", "testing"):
        logging.getLogger(__name__).warning(
            "AUTH_ENABLED=false：全局网关将注入匿名用户并放行所有请求，仅限本地/测试环境"
        )

    @app.before_request
    def require_gateway_jwt():
        """全局鉴权网关（单 Token 子服务模式，见 docs/design/db-to-http-migration/）。

        静态资源与 /login 页面放行；其余请求读取 ``Token`` 请求头
        （兼容 access_token Cookie / ?token= 参数）并经远程 GetUserInfo
        校验，通过后 ``g.current_user`` / ``g.current_token`` 对全部业务
        路由可见。已退役的本地身份/RBAC 接口直接 404。
        """
        from flask import abort, request

        from app.utils.auth import (
            authenticate_current_request,
            is_retired_local_identity_path,
        )

        if request.path.startswith('/static/') or request.path == '/login':
            return None
        if is_retired_local_identity_path(request.path):
            abort(404)
        if request.path in {
            '/api/auth/login',
            '/api/auth/refresh',
            # 登录页/前端启动所需的公共静态配置：无鉴权可读（与本地模式一致）。
            '/api/meta/versions',
            '/api/meta/enums',
            # 兄弟进程内部命令：路由内校验 X-Internal-Secret，不走用户 Token。
            '/api/internal/task-command',
        }:
            return None
        auth_error = authenticate_current_request()
        if auth_error:
            return auth_error
        return None

    @app.teardown_request
    def _clear_request_user_token(exc=None):
        """请求结束清除请求域用户 Token（线程复用防串号，请求域凭据只在请求内有效）。"""
        from app.remote_api.client import clear_request_user_token

        clear_request_user_token()

    @app.context_processor
    def inject_template_auth_context():
        return {
            'auth_enabled': is_auth_enabled(),
        }

    app.notifier = DingTalkNotifier(
        access_token=app.config.get('DING_TALK_ACCESS_TOKEN', ''),
        secret=app.config.get('DING_TALK_SECRET', ''),
    )

    return app
