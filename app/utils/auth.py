"""JWT 认证与权限装饰器"""
import os
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, g
from werkzeug.security import generate_password_hash, check_password_hash

from app.exceptions import UnauthorizedError
from app.repositories import rbac_repository
from app.services.config_manager import get_config_manager

# 开发环境默认 secret 也保持 32+ 字节，避免 JWT 库抛出弱密钥长度告警。
DEFAULT_JWT_SECRET = 'change-me-in-production-secure-key'
SAFE_AUTH_DISABLED_ENVS = {'development'}


def _get_secret():
    """JWT 签名密钥：优先环境变量（部署时固定，重启/换库不变），其次数据库配置，最后默认值。

    启动期 validate_auth_runtime_settings 与本函数读取同一环境变量，
    避免出现"校验用 A、签名用 B"的断裂。
    """
    env_secret = os.environ.get('JWT_SECRET_KEY', '').strip()
    if env_secret:
        return env_secret
    cm = get_config_manager()
    # 环境变量未配置时回退数据库配置/默认值（生产环境应由
    # validate_auth_runtime_settings 在启动期拒绝默认密钥）。
    return cm.get_config('JWT_SECRET_KEY', DEFAULT_JWT_SECRET)


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
                self._perms = set(rbac_repository.list_permission_codes())
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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_auth_enabled():
            _inject_mock_user()
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            raise UnauthorizedError('未提供认证令牌')

        token = auth_header[7:]
        try:
            payload = decode_token(token)
            if payload.get('type') != 'access':
                raise UnauthorizedError('令牌类型错误')
            token_version = extract_token_version(payload)
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError('令牌已过期')
        except jwt.InvalidTokenError:
            raise UnauthorizedError('无效令牌')

        user = rbac_repository.get_user_entity(payload['user_id'])
        if not user or not user.is_active:
            raise UnauthorizedError('用户不存在或已禁用')
        if int(user.token_version or 0) != token_version:
            raise UnauthorizedError('登录状态已失效，请重新登录')

        g.current_user = user
        return f(*args, **kwargs)
    return decorated
