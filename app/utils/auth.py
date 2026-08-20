"""JWT 认证与权限装饰器"""
import os
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from app.services.config_manager import get_config_manager

# 开发环境默认 secret 也保持 32+ 字节，避免 JWT 库抛出弱密钥长度告警。
DEFAULT_JWT_SECRET = 'change-me-in-production-secure-key'
SAFE_AUTH_DISABLED_ENVS = {'development'}
RETIRED_LOCAL_IDENTITY_PREFIXES = (
    '/admin/users',
    '/admin/roles',
    '/admin/navigation',
    '/api/admin/users',
    '/api/admin/roles',
    '/api/admin/permissions',
    '/api/auth/password',
    '/api/navigation-menu-items',
)


def _get_secret():
    """从集中配置读取 JWT 签名密钥。"""
    cm = get_config_manager()
    return cm.get_config('JWT_SECRET_KEY', DEFAULT_JWT_SECRET)


def is_auth_enabled() -> bool:
    """读取认证开关；未配置时默认启用认证。"""
    return os.environ.get('AUTH_ENABLED', 'true').lower() == 'true'


def get_app_env() -> str:
    """读取当前应用环境，并保证返回非空的小写名称。"""
    return os.environ.get('APP_ENV', 'development').strip().lower() or 'development'


def validate_auth_runtime_settings(
    secret: str | None = None,
    auth_enabled: bool | None = None,
    app_env: str | None = None,
) -> None:
    """在非开发环境中尽早拒绝不安全的认证配置。

    本校验只依赖启动期环境变量，因此可在 Flask 扩展和数据库配置初始化前执行。
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

    if resolved_env not in SAFE_AUTH_DISABLED_ENVS and not resolved_auth_enabled:
        raise RuntimeError(
            'AUTH_ENABLED=false is only allowed in development; '
            'refusing to start with authentication disabled.'
        )


def create_access_token(user_id, token_version=0, expires_hours=2):
    """签发包含用户与令牌版本信息的短期访问令牌。"""
    payload = {
        'user_id': user_id,
        'token_version': int(token_version or 0),
        'type': 'access',
        'exp': datetime.utcnow() + timedelta(hours=expires_hours),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm='HS256')


def create_refresh_token(user_id, token_version=0, expires_days=7):
    """签发用于换取访问令牌的长期刷新令牌。"""
    payload = {
        'user_id': user_id,
        'token_version': int(token_version or 0),
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(days=expires_days),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, _get_secret(), algorithm='HS256')


def decode_token(token):
    """使用当前 JWT 密钥校验并解码令牌。"""
    return jwt.decode(token, _get_secret(), algorithms=['HS256'])


def extract_token_version(payload):
    """从令牌载荷读取版本号，不合法的值视为无效令牌。"""
    version = payload.get('token_version', 0)
    try:
        return int(version)
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError('invalid token version')


def is_retired_local_identity_path(path: str) -> bool:
    """确保已废弃的本地身份与 RBAC 接口不会重新暴露。"""
    return any(path == prefix or path.startswith(f'{prefix}/') for prefix in RETIRED_LOCAL_IDENTITY_PREFIXES)


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
            """为关闭认证时的模拟用户返回空权限集合。"""
            return set()

        def to_dict(self, include_permissions=False):
            """将关闭认证时的模拟用户转换为兼容响应字典。"""
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


def authenticate_current_request():
    """校验当前 JWT，并通过 ``sys_user`` 解析令牌主体。

    认证失败时返回 Flask 错误响应，成功时返回 ``None``。
    """
    if hasattr(g, 'current_user'):
        return None
    if not is_auth_enabled():
        _inject_mock_user()
        return None

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'code': 401, 'data': None, 'message': '未提供认证令牌'}), 401

    try:
        payload = decode_token(auth_header[7:])
    except jwt.ExpiredSignatureError:
        return jsonify({'code': 401, 'data': None, 'message': '令牌已过期'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'code': 401, 'data': None, 'message': '无效令牌'}), 401

    user_id = payload.get('user_id', payload.get('userid'))
    if user_id is None:
        return jsonify({'code': 401, 'data': None, 'message': '令牌缺少用户标识'}), 401
    if payload.get('type') not in (None, 'access'):
        return jsonify({'code': 401, 'data': None, 'message': '令牌类型错误'}), 401
    try:
        from app.services.remote_identity_service import RemoteIdentityService
        user = RemoteIdentityService().get_user(user_id, payload.get('username'))
    except Exception:
        return jsonify({'code': 401, 'data': None, 'message': '远程用户校验失败'}), 401
    if not user:
        return jsonify({'code': 401, 'data': None, 'message': '用户不存在或已禁用'}), 401

    g.current_user = user
    try:
        from flask import current_app
        from app.services.model_access_service import set_current_model_codes

        claim_name = current_app.config.get('REMOTE_MODEL_CODES_CLAIM', 'model_codes')
        claimed_codes = payload.get(claim_name)
        if isinstance(claimed_codes, (list, tuple, set)):
            set_current_model_codes(claimed_codes)
    except RuntimeError:
        # Authentication can be used in a bare request context in unit tests.
        pass
    return None


def login_required(f):
    """为路由添加统一认证前置校验。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        """认证成功后调用被装饰的路由函数。"""
        auth_error = authenticate_current_request()
        if auth_error:
            return auth_error
        return f(*args, **kwargs)
    return decorated


# def permission_required(*permission_codes):
#     def decorator(f):
#         @wraps(f)
#         def decorated(*args, **kwargs):
#             if not is_auth_enabled():
#                 return f(*args, **kwargs)
#
#             user = getattr(g, 'current_user', None)
#             if not user:
#                 return jsonify({'code': 401, 'data': None, 'message': '未认证'}), 401
#
#             user_perms = user.get_permissions()
#             required_permissions = [code for code in permission_codes if code]
#             if not any(code in user_perms for code in required_permissions):
#                 missing_permissions = [code for code in required_permissions if code not in user_perms]
#                 if len(required_permissions) <= 1:
#                     required_text = required_permissions[0] if required_permissions else "未配置"
#                     message = f"权限不足，需要权限: {required_text}"
#                 else:
#                     required_text = " 或 ".join(required_permissions)
#                     message = f"权限不足，需要以下任一权限: {required_text}"
#                 if missing_permissions:
#                     message = f"{message}；当前缺少: {'、'.join(missing_permissions)}"
#                 return jsonify({
#                     'code': 403,
#                     'data': {
#                         'required_permissions': required_permissions,
#                         'missing_permissions': missing_permissions,
#                     },
#                     'message': message,
#                 }), 403
#
#             return f(*args, **kwargs)
#         return decorated
#     return decorator

def permission_required(*permission_codes):
    """保留权限声明装饰器，当前实际访问范围由页面模型权限控制。"""
    def decorator(f):
        """包装路由以保持既有权限装饰器调用形式。"""
        @wraps(f)
        def decorated(*args, **kwargs):
            """执行被装饰路由；细粒度接口权限暂未启用。"""
            # 接口权限定义和装饰器保留，当前仅以页面权限控制访问范围。
            # 原接口鉴权代码：
            # user = getattr(g, 'current_user', None)
            # user_perms = user.get_permissions() if user else set()
            # required_permissions = [code for code in permission_codes if code]
            # if not any(code in user_perms for code in required_permissions):
            #     return jsonify({'code': 403, 'data': None, 'message': '权限不足'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
