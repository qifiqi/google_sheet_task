"""JWT 认证、权限装饰器与密码策略"""
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, g, redirect, current_app

from app.exceptions import ForbiddenError, UnauthorizedError
from app.repositories import auth_repository
from app.repositories.stock_sdk import get_user_info
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger

# 公开默认 secret 保持 32+ 字节，避免 JWT 库抛出弱密钥长度告警。
# 该常量只是"显式误配置"的识别标记：_get_secret 的任何解析路径都不会再
# 使用它（等于该值一律视为未配置）；生产环境环境变量显式等于该值时拒绝启动。
DEFAULT_JWT_SECRET = 'change-me-in-production-secure-key'
SAFE_AUTH_DISABLED_ENVS = {'development'}

# 进程内随机兜底密钥：环境变量与数据库都未配置 JWT_SECRET_KEY 时使用。
# 模块导入时生成一次（无 IO，进程内恒定，签名/校验天然一致），从根上杜绝
# 公开常量被用于签名（旧版在此场景 fail-open 回退默认值，令牌可伪造）。
# 代价：进程重启后所有存量令牌失效（用户需重新登录，SSO 用户重新走换票即可）。
_RUNTIME_SECRET = secrets.token_hex(32)

# 页面导航请求无法携带 Authorization 头，登录后由前端把访问令牌同步写入该 cookie，
# 服务端页面鉴权（page_login_required / admin_required）据此回退读取。
# cookie 不按端口隔离，名字必须带项目前缀：本机其他服务签发的同名（尤其 HttpOnly）
# cookie 无法被前端 JS 覆盖，会把页面登录锁死在 302 循环（2026-09 实测踩坑）。
ACCESS_TOKEN_COOKIE = 'gsc_access_token'


def _get_secret():
    """JWT 签名密钥解析：环境变量 → 数据库配置 → 进程内随机密钥。

    - 环境变量优先（部署时固定，重启/换库不变），生产推荐的唯一配置方式；
    - 数据库配置次之（属受保护配置键，HTTP 配置接口无法写入，仅供运维
      经服务端脚本显式设置，可跨重启保持令牌有效）；
    - 两者皆缺省时回退进程内随机密钥。任何路径解析结果等于公开默认常量时
      一律视为未配置，继续向后回退。
    """
    env_secret = os.environ.get('JWT_SECRET_KEY', '').strip()
    if env_secret and env_secret != DEFAULT_JWT_SECRET:
        return env_secret

    db_secret = str(get_config_manager().get_config('JWT_SECRET_KEY', '') or '').strip()
    if db_secret and db_secret != DEFAULT_JWT_SECRET:
        return db_secret

    return _RUNTIME_SECRET


def is_auth_enabled() -> bool:
    return os.environ.get('AUTH_ENABLED', 'true').lower() == 'true'


def get_app_env() -> str:
    return os.environ.get('APP_ENV', 'development').strip().lower() or 'development'


def validate_auth_runtime_settings(
    secret: str | None = None,
    auth_enabled: bool | None = None,
    app_env: str | None = None,
) -> None:
    """Fail fast on unsafe auth settings outside development.

    This validation only uses startup-time configuration (environment variables),
    so it can run before Flask extensions and database-backed config are ready.

    环境变量显式等于公开默认值 → 非开发环境拒绝启动；环境变量未设置 → 不再
    拒绝启动（旧版在此放行、运行期却回退默认密钥，构成 fail-open），改由
    _get_secret 回退进程内随机密钥，这里只输出告警提示运维显式配置。
    """
    resolved_env = (app_env or get_app_env()).strip().lower() or 'development'
    resolved_secret = secret if secret is not None else os.environ.get('JWT_SECRET_KEY')
    resolved_auth_enabled = auth_enabled
    if resolved_auth_enabled is None:
        resolved_auth_enabled = is_auth_enabled()

    if (
        resolved_env not in SAFE_AUTH_DISABLED_ENVS
        and resolved_secret == DEFAULT_JWT_SECRET
    ):
        raise RuntimeError(
            'JWT_SECRET_KEY must be configured outside development; '
            'refusing to use the default insecure secret.'
        )

    if (
        resolved_env not in SAFE_AUTH_DISABLED_ENVS
        and not (resolved_secret or '').strip()
    ):
        get_logger('app.auth').warning(
            'JWT_SECRET_KEY 环境变量未设置：JWT 将使用进程内随机密钥签名，'
            '进程重启后所有已签发令牌失效（用户需重新登录）。'
            '生产部署建议显式设置 JWT_SECRET_KEY。'
        )

    if resolved_env not in SAFE_AUTH_DISABLED_ENVS and not resolved_auth_enabled:
        raise RuntimeError(
            'AUTH_ENABLED=false is only allowed in development; '
            'refusing to start with authentication disabled.'
        )


def create_access_token(user_id, token_version=0, expires_hours=2):
    payload = {
        'user_id': user_id,
        'token_version': int(token_version or 0),
        'type': 'access',
        'exp': datetime.utcnow() + timedelta(hours=expires_hours),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm='HS256')


def create_refresh_token(user_id, token_version=0, expires_days=7):
    payload = {
        'user_id': user_id,
        'token_version': int(token_version or 0),
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(days=expires_days),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm='HS256')


def decode_token(token):
    return jwt.decode(token, _get_secret(), algorithms=['HS256'])


def extract_token_version(payload):
    version = payload.get('token_version', 0)
    try:
        return int(version)
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError('invalid token version')


# ==================== 密码策略 ====================
# 强密码策略：8-64 位，且须同时包含大写字母、小写字母、数字、特殊字符。
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


def validate_password_strength(password: str) -> str | None:
    """强密码校验：合格返回 None，不合格返回用户可读的错误文案。

    纯函数（不抛异常），由服务层决定如何包装成 ValidationError。
    """
    if not password:
        return "密码不能为空"
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"密码长度不能少于{PASSWORD_MIN_LENGTH}位"
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"密码长度不能超过{PASSWORD_MAX_LENGTH}位"

    missing = []
    if not any(c.isupper() for c in password):
        missing.append("大写字母")
    if not any(c.islower() for c in password):
        missing.append("小写字母")
    if not any(c.isdigit() for c in password):
        missing.append("数字")
    if not any(not c.isalnum() for c in password):
        missing.append("特殊字符")
    if missing:
        return "密码须包含" + "、".join(missing)
    return None


def _inject_mock_user():
    """AUTH_ENABLED=false 时注入一个拥有全部权限的 mock 用户，避免下游 g.current_user 报错"""
    if hasattr(g, 'current_user'):
        return

    class _MockUser:
        id = 0
        username = 'anonymous'
        is_active = True
        roles = []
        _perms = None

        def get_permissions(self):
            if self._perms is None:
                # 权限缓存仍留在 auth 层，编码列表来自 repository。
                self._perms = set(auth_repository.list_permission_codes())
            return self._perms

        def to_dict(self, include_permissions=False):
            d = {
                'id': self.id,
                'username': self.username,
                'is_active': self.is_active,
                'created_at': None,
                'last_login': None,
                'roles': [],
            }
            if include_permissions:
                d['permissions'] = sorted(self.get_permissions())
            return d

    g.current_user = _MockUser()


def _extract_request_token():
    """从请求提取访问令牌：优先 Authorization: Bearer 头，其次回退 cookie。

    cookie 回退仅用于页面导航请求（浏览器导航不带自定义头）；
    令牌本就暴露在前端 localStorage，写入非 HttpOnly cookie 不增加暴露面。
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return request.cookies.get(ACCESS_TOKEN_COOKIE) or None


def _resolve_local_token_user(token):
    """本站 JWT 校验：成功返回 (user, None)，失败返回 (None, 用户可见错误文案)。"""
    try:
        payload = decode_token(token)
        if payload.get('type') != 'access':
            return None, '令牌类型错误'
        token_version = extract_token_version(payload)
    except jwt.ExpiredSignatureError:
        return None, '令牌已过期'
    except jwt.InvalidTokenError:
        return None, '无效令牌'

    user = auth_repository.get_user_entity(payload.get('user_id'))
    if not user or not user.is_active:
        return None, '用户不存在或已禁用'
    if int(user.token_version or 0) != token_version:
        return None, '登录状态已失效，请重新登录'

    return user, None


class _ExternalTokenUser:
    """外部 Token（stock_sdk GetUserInfo 校验通过）的请求身份：只读，无本地角色/权限。"""

    def __init__(self, identity):
        self.id = None
        self.username = identity.get('username') or ''
        self.main_userid = identity.get('userid')
        self.is_active = True
        self.roles = []

    def get_permissions(self):
        return set()

    def to_dict(self, include_permissions=False):
        data = {
            'id': self.id,
            'username': self.username,
            'is_active': True,
            'created_at': None,
            'last_login': None,
            'roles': [],
            'external': True,
        }
        if include_permissions:
            data['permissions'] = []
        return data


def _resolve_external_token_user(token):
    """Token 头不是本站 JWT 时回落 stock_sdk GetUserInfo 校验。

    通过返回外部身份，未通过（含网络/HTTP 异常）返回 None；异常详情只进
    日志，令牌本身不落日志。
    """
    try:
        base_url = str(current_app.config.get('STOCK_AUTH_BASE_URL') or '').strip()
        timeout = float(current_app.config.get('STOCK_AUTH_TIMEOUT') or 5)
    except RuntimeError:
        return None
    if not base_url:
        return None

    try:
        identity = get_user_info(token, base_url=base_url, timeout=timeout)
    except Exception as exc:
        get_logger('app.auth').warning('外部令牌校验请求失败: %s', exc)
        return None
    if not identity:
        return None
    return _ExternalTokenUser(identity)


def _resolve_request_user():
    """解析并校验当前请求的用户。

    本站令牌（Authorization Bearer / cookie）优先，语义不变；无本站令牌时
    接受 ``Token`` 头：先按本站 JWT 校验，非本站签发（key 不存在）再经
    stock_sdk GetUserInfo 校验，通过即放行本站接口。
    """
    token = _extract_request_token()
    if token:
        return _resolve_local_token_user(token)

    external_token = request.headers.get('Token', '').strip()
    if not external_token:
        return None, '未提供认证令牌'

    user, error = _resolve_local_token_user(external_token)
    if user is not None:
        return user, None

    external_user = _resolve_external_token_user(external_token)
    if external_user is not None:
        return external_user, None
    return None, error


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_auth_enabled():
            _inject_mock_user()
            return f(*args, **kwargs)

        user, error = _resolve_request_user()
        if user is None:
            raise UnauthorizedError(error)

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def page_login_required(f):
    """页面路由鉴权：与 login_required 同一认证逻辑，未认证重定向登录页而非 401。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_auth_enabled():
            _inject_mock_user()
            return f(*args, **kwargs)

        user, error = _resolve_request_user()
        if user is None:
            next_value = request.full_path if request.query_string else request.path
            from flask import url_for
            return redirect(url_for('auth_pages.login_page', next=next_value))

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def _is_admin_user(user) -> bool:
    """管理员判定：仅做"是否持有 admin 角色"的单一判断（细粒度权限随主服务接入统一解决）。"""
    try:
        return any(getattr(role, 'code', '') == 'admin' for role in (user.roles or []))
    except Exception:
        return False


def admin_required(f):
    """管理端鉴权：login_required 语义 + admin 角色判断；未认证 401，无权限 403。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_auth_enabled():
            # 开发环境关闭鉴权时注入的 mock 用户视为管理员。
            _inject_mock_user()
            return f(*args, **kwargs)

        user, error = _resolve_request_user()
        if user is None:
            raise UnauthorizedError(error)
        if not _is_admin_user(user):
            raise ForbiddenError('需要管理员权限')

        g.current_user = user
        return f(*args, **kwargs)
    return decorated
