# 04 - 统一异常与响应格式设计

> 本设计与数据层重构（README.md）同期落地：统一异常是数据层 `NotFoundError/ConflictError` 的上层承接；统一响应是路由层移除大面积 try/except 样板的前提。两者均随批次推进，见 `03-execution-checklist.md`。

## 1. 现状问题（实测）

### 1.1 三种响应格式并存

| 格式 | 位置 | 使用面 | 前端依赖 |
|---|---|---|---|
| `{"status": "success"\|"error", ...}`（数据键平铺顶层） | routes 10 个文件（task_api / template_api / config_api / google_sheet_api / backtest_multi_product / backtest_training / export_api / global_preview / database_api / stock_api） | 213 处（60 success + 153 error，实测） | `status === 'success'/'error'` 判断 **79 处** |
| `{"code": 0, "data": ..., "message": ...}` | `app/utils/api_response.py` | 仅 `meta_api.py`、`auth_api.py` | `.code === 0` 判断 **3 处** |
| `{"code": 401, "data": None, "message": ...}`（code 语义 = HTTP 状态码） | `app/utils/auth.py` 鉴权装饰器 | 所有 `@login_required` 路由 | `.code === 401` **0 处**（依赖 HTTP 401） |

### 1.2 异常处理混乱

- `create_app()` **未注册任何 errorhandler**；每个 handler 自写 `try/except Exception` + `jsonify({"status": "error"}, 500)` 样板；
- 错误响应直接下发 `str(e)`，会泄漏内部信息（如 SQLAlchemy 原始报错）给客户端；
- `app/exceptions/` 只有 C5 任务域异常（自成体系，带 error_code/details）和空壳 `checkForErrors`；
- 无任何带 HTTP 语义的异常类；数据层原计划自建 `repositories/exceptions.py`，与全局体系将形成两套并存的混乱（本方案取消，见 §3）。

## 2. 统一响应格式（最终契约）

信封为现有三种格式的**超集**，保证前端零破坏：

```json
{
  "status": "success",
  "code": 0,
  "message": "",
  "data": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | `"success" \| "error"` | 保留（前端 79 处判断依据） |
| `code` | `int` | `0`=成功；失败时默认等于 HTTP 状态码，业务需要时可传业务码（`auth.py` 401 已天然符合此语义） |
| `message` | `string` | 用户可见消息；失败时必填 |
| `data` | `object\|list\|null` | 业务数据。**所有端点一律放 `data`**：旧端点迁移时原顶层业务键整体移入 `data`（键名不变），前端读取同批更新 |

- 分页（新端点）统一：`data = {items, total, pages, current_page, per_page}`（由 `paginated()` helper 产出）。
- **无迁移双轨**：不存在 `**top_level` 平铺机制；每个旧端点在其所属批次一次性切换到唯一信封，前端读取（`resp.xxx` → `resp.data.xxx`）与 integration 断言同批更新。

### 2.1 `app/utils/api_response.py` 重写（唯一响应出口）

```python
def success(data=None, message="", http_status=200) -> (jsonify, http_status)
def error(message="操作失败", code=None, http_status=400, data=None)
def paginated(items, total, page, per_page, message="")
```

规则：

1. routes 层只允许经由 `api_response` 产出 JSON 响应；**禁止手写 `{"status": "error", "message": str(e)}`**；
2. `meta_api.py`、`auth_api.py`（`api_response` 仅有的两个消费方）随 B0 重写同批切换（仅响应调用，ORM 不动；`code` 字段保留，前端 3 处判断不破坏）——自 B0 起全库仅存在这一种响应格式；
3. `code` 与 `http_status` 分离：`error("任务不存在", http_status=404)` 自动 `code=404`，业务码可显式覆盖；
4. **无兼容参数**：不提供旧键平铺（`**top_level`）、双格式开关或任何过渡入口。

### 2.2 请求校验（轻量，新文件 `app/utils/request_validation.py`）

```python
def validate_body(required: list[str] | None = None, types: dict[str, type] | None = None) -> dict
    # 校验 JSON body 必填字段与类型，失败抛 ValidationError(message 指明具体字段)
def require_query(name, default=None, cast=None)   # query 参数读取 + 校验
```

- 不引入 pydantic 等重依赖；未来复杂校验需求出现时再评估；
- B1 替换各路由时，把散落的 `if 'name' not in data: return ... 400` 判断收敛为声明式校验（响应仍走统一信封，400 语义不变）；
- 校验失败 → `ValidationError` → 全局处理器 → 400 envelope，路由内不再手写参数错误分支。

## 3. 统一异常体系

### 3.1 层级（`app/exceptions/base.py`，新增）

```
AppException(Exception)
    message: str        # 用户可见消息
    code: int           # 业务码，默认 = http_status
    http_status: int    # 默认 500
    detail: dict|None   # 内部上下文：仅写日志，绝不下发客户端
    log_level: str      # 4xx → "warning"，5xx → "error"

HTTP 语义子类（同一文件）：
    BadRequestError(400) / ValidationError(400) / UnauthorizedError(401)
    ForbiddenError(403) / NotFoundError(404) / ConflictError(409)
    RateLimitError(429) / ServiceError(500)
```

要点：

1. **单一异常体系**：`README.md` 原计划的 `app/repositories/exceptions.py` **取消**；repository 直接 `from app.exceptions import NotFoundError, ConflictError`；
2. 业务域异常按需继承语义子类（如 `TaskNotFoundError(NotFoundError)`），B2+ 随迁移逐步引入，统一放 `app/exceptions/` 下按域分文件；
3. **任务线程域异常不并入**：`C5*Exception`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]` 等看门狗前缀是执行链语义（无 HTTP 语义），保持现状不动（AGENTS.md 已有约定）；
4. `checkForErrors` 空壳保留不动（范围外）。

### 3.2 抛出约定

| 层 | 允许抛出 |
|---|---|
| repositories | `NotFoundError`（get_required/删除/更新目标不存在）、`ConflictError`（唯一约束、状态冲突）；其他一律不翻译，原样上抛 |
| services | 语义子类 + 业务域异常（替代现在"返回 None/错误 dict"的模糊约定） |
| routes | 原则上不 catch；只做参数校验抛 `ValidationError/BadRequestError`，其余交给全局处理器 |

## 4. 全局错误处理器（新文件 `app/errors.py`）

在 `create_app()` 末尾调用 `register_error_handlers(app)`：

```python
@app.errorhandler(AppException)
def handle_app_exception(exc):        # → envelope(exc.http_status, exc.code, exc.message)
    # 按 exc.log_level 记日志，detail 仅入日志

@app.errorhandler(HTTPException)
def handle_http_exception(exc):       # API 路径 → envelope(exc.code, exc.description)
    # 非 API 路径 → 保持 Flask 默认行为（return exc）

@app.errorhandler(Exception)
def handle_unexpected(exc):           # → 500 envelope "服务器内部错误"
    # logger.exception(exc)；绝不 str(e) 下发
    # sqlalchemy.IntegrityError 兜底映射 409（正常应已被 repository 转换）
```

**API 路径判定**：`request.path.startswith("/api")`（页面路由 `/admin`、`/google-sheet` 等保持 Flask 默认 HTML 错误页，UX 不受影响）。

注册后的直接收益：B1 替换每个路由文件时，可直接删除 handler 级 `try/except` 样板（路由层 153 处 `"status": "error"` 大多位于这些样板里），预期异常 raise 语义子类，非预期异常由兜底处理器统一转 500。

## 5. 按批次落地

| 批次 | 动作 |
|---|---|
| B0 | 新增 `app/exceptions/base.py` + `app/errors.py` + `app/utils/request_validation.py`；重写 `app/utils/api_response.py` 并**同批迁移其仅有的两个消费方（`meta_api.py`/`auth_api.py`，仅响应调用，ORM 不动）**；`create_app()` 注册处理器；**AGENTS.md 增补"接口规范"章节（P1-1 交付物：envelope / errorhandler / 校验 / 分层规则 / 无兼容层与仅代码改造原则）**。自 B0 起全库仅一种响应格式；此时无人抛 AppException，API 兜底 500 行为与现状等价，pytest 全绿 |
| B1 | 路由逐文件四合一：repository 替换 + 删 try/except 样板 + 采用 `api_response` + 前端读取/集成测试断言同批更新；URL 与 **HTTP 状态码逐一对齐现状**（含 404/400 语义），响应体切统一信封（数据键移入 `data`） |
| B2–B4 | service 抛业务异常替代错误 dict；repository 抛 `NotFoundError/ConflictError` |
| B5 | `utils/auth.py` 401 改抛 `UnauthorizedError`（前端 0 处 `code===401` 依赖，HTTP 401 不变）；终验（见 §6） |

## 6. 验收

```bash
# 1) routes 内不再手写错误信封（由 api_response/全局处理器产出）
grep -rn '"status": "error"' app/routes --include="*.py"        # 期望 0
# 2) routes 内不再有兜底 catch 样板
grep -rn "except Exception" app/routes --include="*.py"         # 期望仅剩极少数有注释理由的场景
# 3) 数据层异常与全局异常同源
grep -rn "class.*Error\|class.*Exception" app/repositories       # 期望 0（只有 import）
```

红线：任何端点的 HTTP 状态码、`status/message/code` 三键与既有数据键不得变化——以 integration 测试 + 手动冒烟（登录、任务 CRUD、模板 CRUD）为准。
