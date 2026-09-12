# 数据层重构方案（总览）

> 状态：方案已定稿，待执行。执行必须严格遵循本目录下四份文档：
>
> - `README.md` —— 背景、目标、核心设计决策（本文件）
> - `01-db-inventory.md` —— 数据库操作全量清点（按文件 → 模型 → 操作 → 目标 repository → 批次）
> - `02-repository-design.md` —— 数据层详细设计（base 约定、每个 repository 的方法契约）
> - `03-execution-checklist.md` —— 执行清单（批次、步骤、验证命令、回滚方式）
> - `04-exception-response-design.md` —— 统一异常体系与统一响应格式（全局 errorhandler、请求校验）
> - `05-task-runtime-pooling.md` —— P1-2 任务执行池化与任务类型注册表

## 1. 背景

当前项目实际是两层结构：`routes/`（HTTP + 业务 + SQL 混杂）与 `services/`（业务 + SQL 混杂），不存在数据访问层。

实测统计（`grep "db\.session|\.query\."`）：

| 层 | ORM 调用点 | commit 点 |
|---|---|---|
| `app/routes/`（20 文件） | 120 处（集中在 10 个文件） | 24 处 |
| `app/services/`（30+ 文件） | 332 处 | 66 处 |
| `app/utils/` + 外围 | ~68 处（auth/database/db_monitor 等） | 若干 |

典型问题：

- `routes/template_api.py` 内混入任务结果接口（`/api/results*`），直接 join Task/TaskResult 查询；
- `routes/auth_api.py` 全套用户/角色 CRUD 直连 ORM（35 处）；
- `routes/scheduler_api.py` 使用 `get_or_404`，HTTP 语义渗入查询；
- 服务层与路由层都散落 `db.session.commit()`，事务边界不统一；
- 已有 `app/utils/database.py` 的 `safe_create/safe_update` 泛型 helper，本质是伪数据层，调用点分散。

## 2. 目标 / 非目标

**目标：**

1. 所有业务逻辑（routes + services）中的 ORM 操作全部收敛到 `app/repositories/`；
2. 分层清晰：`routes`（HTTP 编排）→ `services`（业务编排）→ `repositories`（独占 ORM）→ `models`；
3. 统一返回 JSON 兼容结构 + 领域异常，为"直连 DB / HTTP 微服务"两种部署形态预留同一接口契约；
4. 接口归属归位（`/api/results*` 移出模板蓝图等），URL 不变；
5. **全量统一、无兼容层**：统一后全库只存在一种响应格式、一种异常体系、一条执行路径——不保留旧格式分支、不加灰度/回退开关、不设过渡双轨 API，每批合入即完成该批范围内的一次性切换（见 §3.6）。

**非目标（明确不做）：**

1. 不改任何 HTTP URL 与请求结构；响应体统一为唯一信封（数据键移入 `data`，前端读取在同批同步更新，见 §3.6）；
2. **不涉及任何数据库修改**：不改 schema、不写迁移、不动表数据，本方案只做代码改造；
3. **不改事务语义**：现有"每步 commit"的断点续跑粒度原样保留（见 §3.3）；
4. `app/startup.py`、`run.py`、`app/navigation.py`（启动播种）、`migrations/`、`tests/`、`scripts/`、`tests/scripts/`、`tests/test/` 不在替换范围；
5. `app/utils/db_monitor.py`、`app/utils/db_optimizer.py`（运维诊断工具，仅 `database_api.py` 使用）保留不动；
6. 模型 `to_dict()` 序列化保留在模型层（它属于数据映射，不属于查询）。

## 3. 核心设计决策

### 3.1 统一返回格式（本方案最重要的契约）

**读路径**：一律返回 **JSON 兼容的原生 Python 结构**——`dict` / `list[dict]` / 标量 / `None`。来源统一为模型 `to_dict()` 或 `with_entities` 投影，repository 内部不做二次包装。

**写路径**：返回更新后的 `dict`，或简单结果（`bool` / 受影响行数 `int`）。

**不存在**：`get_xxx()` 返回 `None`（调用方按现有分支处理）；`get_required_xxx()` 抛 `NotFoundError`（仅替换现有 `get_or_404` 调用点时使用）。

**明确不做 HTTP 风格信封**（`{"status": "success", "data": ...}`）：

- 信封是 HTTP 表现层职责，属于 `routes/` 的 `api_response` 工具；下沉到数据层会污染全部调用方（每个 service 都被迫写 `if r["status"]`）；
- 微服务化映射方式：未来将某 repository 实现替换为 HTTP 客户端时——响应体 `json()` 还原为相同的 dict 结构；HTTP 404 → `NotFoundError`，409 → `ConflictError`，5xx → `RepositoryError`。上层业务代码零改动。

### 3.2 异常体系（统一到 `app/exceptions/`，详见 `04-exception-response-design.md`）

**单一异常体系**，数据层不自建异常：

```
app/exceptions/base.py
AppException(Exception)         # message / code / http_status / detail / log_level
├── NotFoundError               # 实体不存在 → HTTP 404
├── ConflictError               # 唯一约束/状态冲突 → HTTP 409
├── ValidationError / BadRequestError / UnauthorizedError / ForbiddenError / RateLimitError
└── ServiceError(500)
```

- repositories 只抛 `NotFoundError` / `ConflictError`；routes 原则上不自写 try/except 兜底，由 `app/errors.py` 全局 errorhandler 统一转响应信封（仅 API 路径返回 JSON，页面路由保持 Flask 默认）；
- 任务线程域异常（C5*、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]` 等看门狗前缀）无 HTTP 语义，**不并入**，保持现状。

### 3.3 事务语义（红线）

- **写方法默认在方法内部 `commit`**，异常时 `rollback` 后重抛——与现状粒度完全一致；
- 所有写方法带 `commit: bool = True` 参数；跨 repository 的多步原子流程由调用方用 `base.transaction()` 上下文包裹、各步骤传 `commit=False`，由上下文退出时统一提交（仅用于保持现状原子性的场景，如 `auth_api` 删用户时同时清 `user_roles` + `Task.created_by_user_id`）；
- 读方法绝不 commit；
- 禁止在 repository 之外出现任何 `db.session.commit/rollback/query`。

### 3.4 依赖方向与引用规则

```
routes ──▶ services ──▶ repositories ──▶ models
```

- `repositories` 禁止 import `app.services` / `app.routes` / Flask（`request`/`jsonify` 等）；
- `routes` / `services` 替换完成后，禁止直接书写 ORM 查询；从 `app.models` 导入**枚举常量**（`TaskStatus`/`TaskType`/`TaskResultType`/`GoogleSheetTableType` 等）仍允许——它们是常量不是数据访问；
- `SystemConfig` 写路径：repository 只管 DB 行级读写；config_manager 的负缓存刷新仍留在 `config_manager` 层（方向：`config_manager → system_config_repository`，禁止反向 import）。

### 3.5 命名约定

`get_`（单个，可能 None）、`get_required_`（不存在抛 NotFoundError）、`list_`（多个）、`count_`、`exists_`、`create_`、`update_`、`delete_`、`bulk_`、`delete_older_than_`。

### 3.6 统一响应与请求校验（详见 `04-exception-response-design.md`）

- 统一信封 `{status, code, message, data}`：**全库唯一格式**，`status`/`code` 键保留（前端 `status` 判断 79 处、`code===0` 3 处不破坏）；
- **数据一律放 `data`，无 `**top_level` 平铺机制、无迁移双轨**：旧端点在其所属批次一次切换，原顶层业务键整体移入 `data`（键名不变），前端读取与 integration 断言同批更新；
- `app/utils/api_response.py` 重写为唯一响应出口；B0 重写时同批迁移其仅有的两个消费方（`meta_api.py`/`auth_api.py`，仅响应调用），自 B0 起全库仅一种响应格式；
- `app/errors.py` 全局 errorhandler：AppException / HTTPException / 兜底 Exception 三层，仅 API 路径返回 JSON 信封；
- 轻量请求校验 `app/utils/request_validation.py`，失败抛 `ValidationError` → 400。

## 4. 目标目录结构

```
app/repositories/
├── __init__.py                       # 导出全部 repository 单例
├── base.py                           # BaseRepository + transaction() + get_entity 实体访问（任务执行域）
├── task_repository.py                # Task
├── task_result_repository.py         # TaskResult / TaskResultReturn
├── task_log_repository.py            # TaskLog
├── task_template_repository.py       # TaskTemplate
├── system_config_repository.py       # SystemConfig
├── navigation_repository.py          # NavigationMenuItem
├── rbac_repository.py                # User / Role / Permission / user_roles / role_permissions
├── google_sheet_repository.py        # GoogleSheet
├── google_sheet_token_repository.py  # GoogleSheetToken
├── scheduled_task_repository.py      # ScheduledTask
├── stock_metadata_repository.py      # StockMetadata
└── backtest_repository.py            # TaskResultSummaryIndex / BacktestProductResultCache / BacktestSheetRunLock
```

配套新增/重写（统一异常与响应，见 04）：

```
app/exceptions/base.py               # 统一异常层级（单一体系，repositories 直接 import）
app/errors.py                        # 全局 errorhandler（API 路径 JSON 信封）
app/utils/api_response.py            # 重写：唯一响应出口（统一信封 + paginated）
app/utils/request_validation.py      # 轻量请求校验（ValidationError）
```

## 5. 执行阶段总览

| 批次 | 内容 | 风险 | 详见 |
|---|---|---|---|
| P1-3 | MySQL 连接池参数补齐（`config.py` 引擎参数，独立小改动可最先做） | 极低 | 03 §P1 |
| P1-1 | 新接口规范确立并写入 AGENTS.md（envelope + 全局 errorhandler + 请求校验，随 B0 产物落成） | 极低 | 03 §P1 / 04 |
| B0 | 数据层 14 文件 + 统一异常 + 全局 errorhandler + `api_response` 重写（两个既有消费方同批切换）+ 请求校验（除 meta_api/auth_api 响应出口外纯新增） | 极低 | 03 §B0 |
| B1 | 路由层替换（8 个主文件 + 8 个少量文件，含 `/api/results*` 归位 `result_api.py`；删 try/except 样板、采用统一响应，同批更新对应前端读取与集成测试断言） | 低 | 03 §B1 |
| B2 | 服务层常规文件（config_manager、token、scheduler、worker、registry、watchdog、task 子模块读路径等） | 中 | 03 §B2 |
| B3 | 任务执行核心（occupancy → creation/restart → runtime_view → data_cleanup → runtime 最后） | 中高 | 03 §B3 |
| B4 | 执行链与报表（google_sheet_service 系列、backtest 系列、model_summary） | 中高 | 03 §B4 |
| B5 | 外围（auth.py、ding_talk_notifier、ding_stream_service）+ 收尾验证 + 文档更新 | 低 | 03 §B5 |
| P1-2 | 任务执行线程池化 + 并发上限配置 + 任务类型注册表（**前置：B3 完成**） | 中 | 05 |

每批验收标准与回滚方式见 `03-execution-checklist.md`。
