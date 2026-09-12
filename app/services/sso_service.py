"""主服务 SSO 换票服务（docs/design/sso-integration-2026-09/）。

主服务侧边栏携带 Token 跳入子服务 /login#sso_token=...；本服务用该 Token
回调主服务 GetUserInfo 校验（POST，Token 在 header），按返回的
ret_obj.username 同名合并本地账号并签发本地 access/refresh JWT。

主服务 Token 只在换票这一跳出现，之后所有请求走现有 JWT 链路：
login_required / page_login_required / api.js 401 刷新全部不变。
同名合并策略 A：本地已有同名账号直接登录该账号并追加默认角色（不清空
既有角色，同名管理员仍保留管理员权限）；禁用账号拒绝 SSO，不自动启用。

SSRF 约束（Mimosa 审计要求，服务端请求外部 URL 的统一做法）：
- 仅允许 HTTPS 明文主机名 URL，禁带 userinfo；
- 解析域名后拒绝私网/环回/链路本地/保留地址（仅公网 IP 可达）；
- 禁用重定向与请求库代理环境变量，防止借 302 或代理绕过 IP 边界；
- DNS rebinding 由 TLS 证书校验兜底：内网主机无法持有主服务域名的合法证书。
"""

import ipaddress
import socket
import secrets
from datetime import datetime
from urllib.parse import urlsplit

import requests
from flask import current_app
from werkzeug.security import generate_password_hash

from app.config import SSO_ROLE
from app.exceptions import ServiceError, UnauthorizedError
from app.repositories import auth_repository
from app.utils.auth import create_access_token, create_refresh_token
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _validate_verify_url(url: str) -> str:
    """校验主服务校验接口 URL：仅接受公网 HTTPS 主机名地址，返回规范化 URL。"""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ServiceError('主服务校验接口地址非法', detail=f'url={url!r}') from exc

    if parts.scheme != 'https' or not parts.hostname:
        raise ServiceError(
            '主服务校验接口必须为 https 地址',
            detail=f'scheme={parts.scheme!r} hostname={parts.hostname!r}',
        )
    if parts.username or parts.password:
        raise ServiceError('主服务校验接口地址非法', detail='userinfo not allowed')

    try:
        infos = socket.getaddrinfo(parts.hostname, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ServiceError('主服务域名解析失败', detail=f'{parts.hostname}: {exc}') from exc

    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise ServiceError(
                '主服务地址非法（非公网地址）',
                detail=f'{parts.hostname} resolved to {addr}',
            )
    return url


def verify_token_with_main_service(token: str) -> dict:
    """调主服务校验接口验证 Token，成功返回 {'username', 'userid'}。

    任何失败路径都抛异常，绝不降级放行：令牌无效 → UnauthorizedError(401)；
    网络/超时/响应结构异常 → ServiceError(500)。上游响应正文只进日志
    detail，不下发客户端。
    """
    raw_url = (current_app.config.get('SSO_MAIN_VERIFY_URL') or '').strip()
    url = _validate_verify_url(raw_url)
    timeout = int(current_app.config.get('SSO_MAIN_VERIFY_TIMEOUT') or 5)

    try:
        # 直连已校验的公网 HTTPS 端点：禁重定向（302 不得改道内网）、
        # 禁请求库代理环境变量（本仓库行情链路会配代理，SSO 校验不走）。
        resp = requests.post(
            url,
            headers={'Token': token},
            timeout=timeout,
            allow_redirects=False,
            proxies={'http': None, 'https': None},
            verify=True,
        )
    except requests.Timeout as exc:
        raise ServiceError('主服务校验接口超时', detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise ServiceError('主服务校验接口不可达', detail=str(exc)) from exc

    if resp.status_code in (401, 403):
        raise UnauthorizedError('主服务令牌无效或已过期')
    if resp.status_code != 200:
        raise ServiceError('主服务校验接口异常', detail=f'HTTP {resp.status_code}')

    try:
        body = resp.json()
    except ValueError as exc:
        raise ServiceError('主服务校验响应格式异常', detail=resp.text[:200]) from exc

    obj = body.get('ret_obj') or {}
    username = str(obj.get('username') or '').strip()
    if body.get('ret_code') != 200 or not username:
        # 主服务契约：HTTP 200 + ret_code 表达业务结果；非 200 视为令牌未通过。
        raise UnauthorizedError('主服务令牌无效或已过期')
    return {'username': username, 'userid': obj.get('userid')}


def exchange_sso_token(token: str) -> dict:
    """主服务 Token → 本地账号 → 本地 JWT 双令牌。

    返回结构与 auth_service.login_user 完全一致（access_token/refresh_token/
    user），前端复用同一套 setTokens 管线。重复换票幂等：同名账号与默认角色
    关系不会因多次换票而重复或丢失。
    """
    if not token or not token.strip():
        raise UnauthorizedError('未提供主服务令牌')
    if not current_app.config.get('SSO_ENABLED'):
        raise ServiceError('主服务登录未启用')

    identity = verify_token_with_main_service(token.strip())
    user = _resolve_sso_user(identity)
    auth_repository.update_last_login(user.id, datetime.now())
    logger.info(
        'SSO 换票成功: username=%s main_userid=%s user_id=%s',
        user.username, identity.get('userid'), user.id,
    )
    return {
        'access_token': create_access_token(user.id, token_version=int(user.token_version or 0)),
        'refresh_token': create_refresh_token(user.id, token_version=int(user.token_version or 0)),
        'user': auth_repository.get_user(user.id, include_permissions=True),
    }


def _resolve_sso_user(identity: dict):
    """按 username 定位本地账号：无则建号挂默认角色，有则并集追加默认角色。"""
    username = identity['username']
    role_id = auth_repository.get_role_id_by_code(SSO_ROLE['code'])

    user = auth_repository.get_user_entity_by_username(username)
    if user is None:
        # 首次 SSO 进入：随机不可用密码建号（不走密码登录，防撞库接管）。
        if not role_id:
            raise ServiceError(
                'SSO 默认角色缺失',
                detail=f"role {SSO_ROLE['code']} not seeded; run `flask init-rbac` to seed it",
            )
        created = auth_repository.create_user(
            username,
            generate_password_hash(secrets.token_hex(32)),
            role_ids=[role_id],
            is_active=True,
        )
        logger.info('SSO 首次进入自动建号: username=%s user_id=%s', username, created['id'])
        return auth_repository.get_user_entity_by_username(username)

    if not user.is_active:
        raise UnauthorizedError('账号已被禁用，请联系管理员')
    # 同名合并策略 A：保留既有角色，仅确保默认角色在列（管理员同名号不受影响）。
    if role_id:
        auth_repository.append_user_role(user.id, role_id)
    return user
