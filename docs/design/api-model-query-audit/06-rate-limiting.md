# 06 — API 保护性限流设计

> 结论先行：**有必要，但范围收窄为"保护性限流"，明确不做全局 QPS 限流**。本系统是登录后的任务平台，全局限流只会误伤前端合法轮询（日志 3s / 任务列表 15s / 仪表盘 30s 均为可配置的正常高频流量）。
>
> **边界（2026-09-05）**：登录防爆破属鉴权域，将随登录体系整体迁移主服务（`07` §1.2）——本分册只保留与鉴权无关的**服务保护限流**（重计算/导出端点），登录项降级为过渡期可选。

## 1. 必要性判定（基于代码事实）

| 端点/场景 | 现状 | 风险 | 判定 |
|---|---|---|---|
| `/api/auth/login` | `auth_api.py:53-78`：**无限次**密码尝试，无失败锁定、无频率限制 | 内网弱口令爆破 / 脚本撞库 | **过渡期可选**（登录体系将整体迁移主服务，见 `07` §1.2；仅当过渡期公网暴露 login 时挂载） |
| 重计算端点：`/xpl/analyze`、`/v1/analyze`、bt/bmp `/api/import-excel`、`/api/global-preview/<id>/calculate-ratios`、`/api/model-summary/rebuild` | 无限制；analyze 是纯计算、import 解析 Excel、rebuild 全量重建汇总 | 用户重复点击造成 CPU/内存尖峰（误伤自己） | **P2** |
| 大数据导出：`/api/exports/*`、export-preview 下载 | 无限制；单次拉取全量结果行 | 误触风暴拖垮 worker | **P2** |
| 任务创建：`/api/tasks` POST、`/tasks/batch-create` | 无限制，但已有 `max_concurrent_tasks=20` 配额兜底 | 低 | **P3 可选** |
| 其余 80+ 端点 | — | 前端轮询本就是高频合法流量 | **不限流** |

## 2. 实现选型：Flask-Limiter（用户决策 2026-09-05，不自行实现）

引入 `Flask-Limiter`（依赖 `limits`），内存存储起步。设计要点：

```python
# app/extensions.py（或 create_app 内）
from flask_limiter import Limiter

limiter = Limiter(
    key_func=get_remote_address,      # 全局默认键仅兜底；实际端点逐个覆盖（见下）
    storage_uri="memory://",          # 单进程精确；Gunicorn 多 worker 见 §5
    default_limits=[],                # ★ 不设全局限流——前端轮询是合法高频流量
    headers_enabled=True,             # 响应带 X-RateLimit-* 头，便于前端展示
)
```

```python
# 端点挂载示例（重计算端点，阈值经 config_manager 运行时可调）
@export_api_bp.route("/tasks/<task_id>", methods=["GET"])
@login_required
@limiter.limit(lambda: f"{get_config('rate_limit_export', 10) or 10}/minute",
               key_func=lambda: f"user:{g.current_user.id}")
def export_task(task_id): ...
```

- **键函数用用户维度而非 IP**：全库无 `ProxyFix`/`X-Forwarded-For` 处理（已 grep 证实），nginx 模式下 `remote_addr` 恒为代理地址，默认的 `get_remote_address` 会把全体用户并成一个桶——**每个挂载端点必须显式覆盖 `key_func`**（登录键取 `request.get_json(silent=True)` 的 username，其余取 `g.current_user.id`）；
- **装饰器顺序强制**：`@bp.route` → `@login_required` → `@limiter.limit(...)` → 函数内 `parse_body`（限流键依赖 `g.current_user`，鉴权必须先执行；Pydantic 校验最后，400 优先于 429）；
- **429 信封**：超限抛 `RateLimitExceeded`（`werkzeug` HTTPException 子类，code=429），在 `errors.py` 增加专用 handler 统一中文文案：

  ```python
  from limits.errors import RateLimitExceeded

  @app.errorhandler(RateLimitExceeded)
  def handle_rate_limited(exc):
      return error("请求过于频繁，请稍后重试", http_status=429)
  ```

  （不加该 handler 也会被现有 `HTTPException` handler 兜住转信封，但消息是英文的 "1 per 10 seconds"——专用 handler 是为了文案，不是必需件。）
- **阈值动态化**：flask-limiter 的 limit 值支持 callable（上例），从 `config_manager.get_config` 读取，运行时可调零重启；配置键播种进 `config.py::init_config`（`04` 分册同款风格）；
- **测试环境**：`TestingConfig` 置 `RATELIMIT_ENABLED=False`（或测试用例里 `limiter.reset()`），避免用例间互相污染；
- login（过渡期可选）若挂载：`key_func=lambda: (request.get_json(silent=True) or {}).get("username", "")`。

## 3. 端点挂载清单（阈值默认值，进 SystemConfig 可调）

| 端点 | 限制（每窗口） | 键 | 配置键 |
|---|---|---|---|
| `/api/auth/login`（**过渡期可选**，默认不挂载——登录将迁移主服务） | 10 / 60s | username | `rate_limit_login` |
| `/xpl/analyze`、`/v1/analyze` | 10 / 60s | user | `rate_limit_analyze` |
| bt/bmp `/api/import-excel`、`/api/global-preview/<id>/calculate-ratios` | 6 / 60s | user | `rate_limit_heavy` |
| `/api/model-summary/rebuild` | 2 / 60s | user | `rate_limit_rebuild` |
| `/api/exports/*`、`/api/task-result/<id>/export-preview` | 10 / 60s | user | `rate_limit_export` |
| `/api/tasks` POST、`/tasks/batch-create`（P3 可选） | 10 / 60s | user | `rate_limit_task_create` |

- 配置经 `config_manager`（`config.py` `init_config` 播种默认值，消费方 `coerce_int` 读取），阈值运行时可调、零重启；
- 装饰器从 `SystemConfig` 读阈值需避免每请求查库——`config_manager` 本身带缓存，直接 `get_config` 即可（负缓存/线程安全既有保证）。

## 4. nginx 模式的兜底层（可选，模式 A 部署时）

```nginx
# IP 级粗粒度兜底，只挂在 login（防分布式撞库的最后一道），不影响已登录流量
limit_req_zone $binary_remote_addr zone=login:10m rate=30r/m;
location = /api/auth/login { limit_req zone=login burst=10 nodelay; proxy_pass …; }
```

Flask 层的 username 键不受代理影响，是主防线；nginx 层为可选加固，不作为依赖项。

## 5. 多 worker 注意（Gunicorn 部署）

`dockers/gunicorn.conf.py` 多 worker 时 `memory://` 存储不共享，实际限值 ≈ 配置 × worker 数。保护性限流对此不敏感（目的是挡风暴不是精确计量）；若未来需要精确全局计量，`RATELIMIT_STORAGE_URI` 切到 `redis://` 即可，业务代码零改动——该扩展**现在不做**。

## 6. 测试

- 集成：login（若挂载）/analyze 连续超限请求返回 429 信封（`status=error`、`code=429`、中文 message）；带 token 的正常流量不受影响；
- `TestingConfig` 中 `RATELIMIT_ENABLED=False`，既有集成测试全部不受限流影响；限流本身的行为（窗口/键隔离/headers）信任 flask-limiter，不重复测库；
- 回归：前端轮询路径（`/api/tasks` GET、`/api/logs/latest`）确认未挂限流，15s/3s 轮询不受影响。

## 7. 与其他分册的衔接

- 限流装饰器挂在**路由函数**上（`01` §5 的 xpl 改造批同批挂载，避免两个批改同一文件）；
- `05` 的 Pydantic 校验先于限流执行（解析失败 400 优先于 429），装饰器顺序：`@bp.route` → `@login_required` → `@rate_limit` → 函数内 `parse_body`；
- 阈值配置键在 `config.py::init_config` 播种（`04` 分册的配置化风格一致）。
