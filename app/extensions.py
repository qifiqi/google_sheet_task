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
