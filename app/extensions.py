from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()

# 保护性限流（docs/design/api-model-query-audit/06）：
# memory:// 单进程精确；default_limits 为空——不设全局限流，前端轮询不受影响；
# 端点级键函数必须显式覆盖（nginx 下 remote_addr 恒为代理地址）。
limiter = Limiter(
    key_func=lambda: "global",
    storage_uri="memory://",
    default_limits=[],
    headers_enabled=True,
)


def rate_limit_config(config_key, default):
    """端点级限流阈值经 config_manager 运行时可调（零重启）。"""
    from app.services.config_manager import get_config_manager

    return get_config_manager().get_config(config_key, default)


def rate_limit_user_key():
    """端点级限流键：登录用户按 id，未登录归 anon。"""
    from flask import g

    return f"user:{getattr(getattr(g, 'current_user', None), 'id', 'anon')}"
