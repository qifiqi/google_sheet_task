# AGENTS.md

本文件用于指导 Codex / 代码代理在本仓库内工作。目标不是解释 Flask 基础概念，而是帮助代理快速理解这个项目的真实结构、常见风险点和推荐操作方式。

## 项目定位

这是一个基于 Flask 的任务执行平台，核心能力包括：

- Google Sheet 参数任务执行
- C3 / C4 / C5 多模板任务
- C31 批量拆分为多个 C3 子任务
- backtest_training 回测训练任务
- 任务调度、看门狗、断点重启
- Google Sheet token / sheet 资源占用管理
- 管理后台、模板系统、任务日志和结果查询

仓库明显以“长时间运行的任务系统”而不是“纯同步 Web CRUD”作为主线，因此任何修改都要优先考虑：

- 线程生命周期
- 数据库状态和内存状态一致性
- Token / Google Sheet 占用释放
- 失败后的可恢复性
- 网络抖动下的重试和重连

## 启动与常用命令

### Windows PowerShell 编码

仓库包含大量中文模板和注释。在 Windows PowerShell 里读取文件时，默认编码经常导致乱码。

推荐先执行：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
```

读取文件时始终显式使用 UTF-8：

```powershell
Get-Content .\run.py -Encoding UTF8
Get-Content .\templates\google_sheet_c31\create.html -Encoding UTF8
```

### 本地运行

```bash
python run.py
```

### 安装依赖

```bash
pip install -r requirements.txt
```

### 数据库相关

```bash
flask db init
flask db migrate -m "message"
flask db upgrade
```

注意：本项目并不总是完全依赖标准迁移流。`run.py` 里还包含若干启动时 schema 修补逻辑，因此遇到线上脏库问题时要先看 `run.py`。

### 测试（2026-08-29 重组后）

```bash
pip install -r requirements-dev.txt   # pytest（运行依赖不变）
pytest                                 # 全量：tests/unit + tests/integration
pytest tests/unit/test_p0_p1_refactor.py::test_name   # 定向
```

目录结构：

- `tests/unit/`：服务、工具、模型层单元测试（主力回归入口 `tests/unit/test_p0_p1_refactor.py`）
- `tests/integration/`：通过 Flask test_client 的接口与页面集成测试
- `tests/archive/`：历史备份（legacy_services、旧模板拷贝、demos 等），`pytest.ini` 的
  `norecursedirs` 已排除，不参与收集，不要在里面新增正式测试
- `pytest.ini`：统一配置。`addopts` 带 `--basetemp=.pytest_tmp`，用于绕开本机系统
  Temp 目录 ACL 损坏（否则 setup 阶段报 `PermissionError: [WinError 5]`）

约定：

- 新增测试按层放入 `unit/` 或 `integration/`；修改 K 线/搜索相关测试时，fake 的东方财富
  搜索结果必须含 `code`/`market`/`status`/`shortName`（`StockSearchService._normalize_result` 契约）
- `tests/unit/test_xpl_service.py`、`tests/unit/test_backtest_training_export.py`、
  `tests/integration/test_backtest_training_export_preview.py`、
  `tests/unit/test_model_summary_service.py` 中有 10 个 `@pytest.mark.skip` 用例，
  对应未完成的项目代码修复（metrics 日度分布/月度基线、超额回撤符号约定、
  export-preview download 路由未注册、CSV Content-Type 重复 charset），修复后取消 skip
- requirements.txt 仍不含 pytest，测试依赖装在 requirements-dev.txt
- `tests/` 根目录残留与 `tests/unit/`、`tests/integration/` 同名的历史测试文件，
  直接跑 `pytest` 会因模块名冲突收集报错；全量回归统一用
  `python -m pytest tests/unit tests/integration`

## 接口规范（2026-09 数据层重构确立）

设计文档：`docs/design/data-layer-refactor/`（README + 01~05）。总原则：**全程不涉及数据库修改**
（不改 schema/迁移/数据）；**全库无兼容层**（单一响应格式、单一异常体系、单一执行路径，
无灰度/回退/双轨开关）。

### 统一响应信封（全库唯一格式）

```json
{"status": "success", "code": 0, "message": "", "data": null}
```

- 唯一出口是 `app/utils/api_response.py` 的 `success()` / `error()` / `paginated()`；
  **routes 禁止手写 `{"status": "error", ...}` 字典**；
- 所有业务数据一律放 `data`（键名不变），无顶层平铺机制；
- `code` 失败时默认等于 HTTP 状态码，业务码可显式覆盖；分页 data 统一
  `{items, total, pages, current_page, per_page}`（`paginated()` 产出）。

### 统一异常体系（`app/exceptions/base.py`，单一体系）

- `AppException(message, code, http_status, detail, log_level)` 层级：
  BadRequest/Validation(400)、Unauthorized(401)、Forbidden(403)、NotFound(404)、
  Conflict(409)、RateLimit(429)、ServiceError(500)；
- repositories 只抛 `NotFoundError` / `ConflictError`（其他异常原样上抛，保留异常链）；
- services 抛语义/业务域子类；routes 原则上不 catch，交给全局处理器；
- **任务线程域异常不并入**：`C5*`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]`
  前缀是执行链语义（无 HTTP 语义），保持现状。

### 全局错误处理器（`app/errors.py`，create_app 末尾注册）

- 仅 `request.path.startswith("/api")` 返回 JSON 信封；页面路由保持 Flask 默认 HTML 错误页；
- 兜底 `Exception` → 500 `"服务器内部错误"`，**绝不 `str(e)` 下发**；IntegrityError 兜底 409。

### 请求校验（2026-09-05 起：Pydantic v2）

- `app/schemas/`（APIModel 基类 + PageQuery + 按域模块）与
  `app/utils/request_parsing.py`（parse_body/parse_query）；
  解析失败就地转 `ValidationError` → 400 信封（`errors.py` 零改动）；
- 旧 `request_validation.py` 已删除（无兼容层，见 api-model-query-audit/05）；
- 保护性限流：Flask-Limiter（`app/extensions.py::limiter`，memory://，
  default_limits 为空不做全局限流）；429 走专用中文信封 handler；
  阈值经 config_manager 运行时可调（rate_limit_* 配置键）。

### 鉴权边界与子服务化（2026-09-05 决策）

- 本项目后续作为**子服务接入主服务**：路由网关、鉴权、权限、角色、登录**整体迁移主服务**；
- 当前 RBAC/JWT（`t_param_user/role/permission`、`app/utils/auth.py`、`template-auth.js`）
  是内部项目时期的历史产物，**不再新增权限类建设**；已知缺口（admin 类 API 仅校验登录、
  登录无防爆破、xpl 端点未挂鉴权）登记于
  `docs/design/api-model-query-audit/07-public-deployment-and-subservice.md` §1，随主服务接入统一解决；
- 保持两个迁移接缝单一：服务端鉴权只经 `login_required` 装饰器入口，前端鉴权只经
  `template-auth.js`；新增路由/页面不得自写鉴权逻辑；
- API 限流使用 **Flask-Limiter**（内存存储、user/username 键函数、429 走统一信封），
  不自行实现限流算法；全库不做全局限流，前端轮询路径不挂限流。

### 数据层分层规则（repositories 独占 ORM）

- 分层方向：`routes`（HTTP 编排）→ `services`（业务编排）→ `repositories`（独占 ORM）→ `models`；
- routes/services 内**禁止直接书写 ORM 查询**（`db.session` / `Model.query`）；
  从 `app.models` import 枚举常量（`TaskStatus`/`TaskType` 等）允许；
- routes **禁止直接 import / 调用 repository**（2026-09-05 R 系列收编后生效）：
  路由一律经 service 访问数据（任务读走 task_manager 门面、模板走 task_template_service、
  导航走 navigation_service、RBAC 走 rbac_service、配置走 config_manager 等），
  终验 `grep -rn "from app\.repositories\|_repository\." app/routes` 为空；
- `app/repositories/` 命名约定：`get_`（可 None）/ `get_required_`（抛 NotFoundError）/
  `list_` / `count_` / `exists_` / `create_` / `update_` / `delete_` / `bulk_` / `delete_older_than_`；
  领域动词补录（2026-09-05 审计批 D）：`upsert_`（唯一键幂等写）、`acquire_` / `release_` /
  `occupy`（锁与占用记账）、`mark_` / `revert_` / `record_`（状态机与运行记录）、
  `dedupe_`（窗口去重写）、`refresh_entity`（会话重挂）、`sum_`（聚合读）、
  `apply_`（批量记账）——这些语义硬套 CRUD 前缀会失真，视为合法前缀；
- 写方法默认方法内 commit、签名带 `commit: bool = True`，异常 rollback 后裸 `raise`；
  读方法绝不 commit；跨 repository 原子流程用 `base.transaction()` 包裹、各步骤传 `commit=False`；
- 读路径返回 JSON 兼容原生结构（`to_dict()` / 投影），信封不下沉数据层；
  `get_entity()` 仅任务执行域（runtime 线程目标）使用；
- repositories 禁止 import `app.services` / `app.routes` / Flask；
- `SystemConfig` 写路径：repository 只管行级读写，负缓存刷新留在 `config_manager`
  （方向 config_manager → repository，禁止反向 import）；
- `app/startup.py`、`run.py`、`app/navigation.py`（启动播种）、`migrations/`、
  `tests/`、`scripts/` 不在替换范围；`app/utils/db_monitor.py`、`db_optimizer.py` 保留。


## 真实入口与启动流程

### 应用工厂

`app/__init__.py`

- `create_app()` 创建 Flask 应用
- 通过 `load_app_environment()` 按顺序加载 `.env` 和 `.env.{APP_ENV}`
- 初始化 `db`、`migrate`
- 初始化 `config_manager`
- 注册蓝图
- 初始化钉钉通知器

### 运行入口

`run.py`

启动编排已整体下沉到 `app/startup.py`，`run.py` 只负责创建应用并调用 `bootstrap_app(app)`。`bootstrap_app` 依次执行：

- `_prepare_runtime_directories()` / `initialize_logging()`
- `_recover_runtime_resources()`：重置 token / Google Sheet 占用与回测锁（进程内状态）
- `_initialize_system_metadata()`：幂等播种默认配置（`init_config`）、RBAC（`init_rbac`，含默认管理员）和导航菜单
- `check_and_cleanup_dead_tasks(app)`：把数据库里 running 但本进程无线程的任务重置为待启动
- `_start_background_components(app)`：调度器 + 任务看门狗线程

注意：

- 表结构不在启动期创建。新环境需先执行 `flask init_db`（兼容兜底）或 `flask db upgrade`（标准迁移），否则 `_initialize_system_metadata()` 会因缺表失败。
- `_initialize_database_schema()` 在 `bootstrap_app` 中保持注释状态，仅在 CLI `flask init_db` 中调用。

任何影响任务状态、token 占用、RBAC、用户字段、看门狗行为的修改，都要同时评估：

- `run.py`
- `app/startup.py`

## 路由与前端页面

蓝图注册在 `app/routes/__init__.py`。

主要蓝图：

- `admin_bp` -> `/admin`
- `task_api_bp` -> `/api`
- `config_api_bp` -> `/api`
- `template_api_bp` -> `/api`
- `google_sheet_api_bp` -> `/api`
- `database_api_bp` -> `/api`
- `google_sheet_bp` -> `/google-sheet`
- `scheduler_api_bp` -> 根路径下调度接口
- `backtest_training_bp` -> 回测训练页面和接口
- `xpl_bp` -> `/xpl`
- `yule_bp` -> `/yule`

模板目录重点关注：

- `templates/google_sheet/create.html`：C3 创建页
- `templates/google_sheet_c4/create.html`
- `templates/google_sheet_c5/create.html`
- `templates/google_sheet_c31/create.html`：C31 批量创建页
- `templates/backtest_training/create.html`
- `templates/admin/*`

前端页面里有大量内联 JavaScript，且存在“初始化后再重建部分 DOM”的写法。修改字段时不要只改静态 HTML，必须同时检查：

- 表单初始化逻辑
- localStorage 恢复逻辑
- 模板回填逻辑
- restart 回填逻辑
- 提交 payload 逻辑

## 数据访问（2026-09 重构落地）

- `app/repositories/` 是唯一 ORM 层；routes/services 已全部迁移（2026-09-05 审计批 A~D
  收尾复验：ORM 精确 grep 与服务层手写信封均为 0，执行记录见
  `docs/design/data-layer-refactor/03-execution-checklist.md`）；
- 路由直连 repository 已收编（2026-09-05 R1~R5 批次）：路由零 repository import，
  读路径统一经 service（新增 task_template_service / navigation_service /
  rbac_service；task 门面补 get_task/get_required_task 等只读入口），执行记录同上；
- 响应信封/异常/校验/分层细则见上文“接口规范”章节；
- `app/utils/database.py` 的 safe_create/safe_update 已弃用（调用点清零），
  transaction_required 仍被 creation/restart/stock_metadata 使用（提交重试语义）。

## 任务系统核心

### 任务主控门面

当前真实入口已经不是旧的 `app/services/task_manager.py`，而是：

- `app/services/task/facade.py`
- `app/services/task/__init__.py`

对外仍然使用 `TaskManager` / `task_manager`，但内部已经拆成多个 mixin 文件。

负责：

- 创建任务
- 启动任务线程
- C31 批量拆分为多个 C3 子任务
- 重启任务
- 本地线程状态检查
- Token 和 Google Sheet 占用管理

门面内部重点运行态数据结构仍然包括：

- `running_tasks`: `task_id -> thread`
- `task_stop_events`: `task_id -> threading.Event`
- `start_errors`
- `task_token_occupancy`

修改任务执行相关逻辑时，必须同时检查：

- `app/services/task/runtime.py`
  - `start_task()`
  - `_execute_google_sheet_task()`
  - `_execute_google_sheet_c4_task()`
  - `_execute_google_sheet_c5_task()`
  - `_execute_backtest_training_task()`
- `app/services/task/creation.py`
  - `create_task()`
  - `batch_create_and_start_task()`
- `app/services/task/restart.py`
  - `cancel_task()`
  - `restart_task()`
- `app/services/task/occupancy.py`

额外说明：

- `tests/archive/legacy_services/task_manager.py` 只是兼容层，不是生产实现
- 如果文档、脚本或测试还引用旧 `app/services/task_manager.py`，要优先确认是否只是历史残留表述

### C31 特殊逻辑

`google_sheet_C31` 不是独立执行器，而是前端批量创建页。最终会在 `TaskManager.batch_create_and_start_task()` 中拆成多个 `google_sheet` 子任务。

因此如果 C31 页面新增字段需要真正参与执行：

1. 前端提交到 `config`
2. `batch_create_and_start_task()` 透传到每个 `child_config`
3. 真正消费字段的服务（通常是 `google_sheet_service.py`）读取该字段

只改前端或者只改 service 都不够。

## Google Sheet 执行链路

### 客户端

`app/services/google_sheet_client.py`

这是 Google Sheet 网络 IO 的底层封装，基于：

- `gspread`
- `google.oauth2.credentials.Credentials`

现有实现包含：

- 自动设置 HTTP timeout
- 代理注入
- worksheet 选择
- 网络错误识别
- 网络重试
- 重连逻辑

近期已补充：

- 对可恢复网络错误显式抛出 `RetryableNetworkTaskError`
- 网络重试耗尽后向任务层暴露“可自动重启”的错误类型

如果任务因为网络问题失效，优先改这里，而不是在上层大量加散乱 `try/except`。

### 东方财富 / 股票检索链路

近期和回测任务直接相关的网络入口还包括：

- `app/utils/dfcf_api.py`
- `app/utils/proxy_manager.py`

当前实现特征：

- 股票搜索优先走 codetable，失败后回退 suggest
- K 线请求是否启用代理由配置项 `dfcf_kline_proxy_enabled` 控制
- 回测训练任务会把 `market_type` 规范化为 `cn` / `en`

如果是“股票搜索不到 / K线拉取失败 / 美股与A股市场代码错传”这一类问题，优先检查这里，再看上层页面和 service。

### 业务服务

- `app/services/google_sheet_service.py`：C3
- `app/services/google_sheet_service_C4.py`
- `app/services/google_sheet_service_C5.py`
- `app/services/google_sheet_service_C7.py`
- `app/services/backtest_training_service.py`

这些服务的共同模式：

- 在 `execute_task()` 中加载任务配置
- 初始化 Google Sheet 连接
- 逐步执行参数组合
- 保存 `TaskResult`
- 写 `TaskLog`
- 支持取消和断点恢复

注意事项：

- 这些服务都在后台线程中运行
- 失败信息最终会回写到 `Task.error_message`
- 网络异常已通过统一工具打标，可被看门狗自动识别

### C5 / C7 自定义K线模式

C5 / C7 支持 `config.kline_source`：

- `auto`：默认模式，按 `market_type`、`price_mode`、`kline_adjustment`、日期区间等配置自动获取并转换K线。
- `custom`：任务级开关，表示用户已经在 Google Sheet 输入列维护好K线。后端不再调用 `_get_all_parameters()` 的自动行情链路，不请求东方财富 / Yahoo，不做复权、日期区间拆分或K线转换。

`custom` 模式的执行约束：

- 只在 `get_bdl()` 预计算阶段读取一次现有 Sheet 输入列，构造 `Kline_key=custom` 的参数组合。
- 执行参数组合时只写入 `xm` / `ml` 等参数，不清空、不重写K线输入列。
- 仍会读取现有K线行数，用于确定收益序列读取范围和 `TaskResult.parameters.kline` 的首尾日期。
- `TaskCreationMixin._normalize_task_config_for_type()` 会把 `market_type` 归一为 `custom`，并禁用 `price_mode`、`kline_adjustment`、`date_range_mode`、`exclude_recent_years`、`start_date`、`end_date` 等自动K线选项。

修改 C5 / C7 K线相关逻辑时，不要把 `custom` 分支放进 `_get_all_parameters()` 的内部判断；那会重新进入自动K线获取/转换链路，违背自定义K线模式的任务级语义。

## 看门狗与自动恢复

`app/services/task_watchdog.py`

看门狗会定期检查任务状态。当前策略重点包括：

- 检查最近 5 天创建的任务
- 检查 `running` 任务是否长时间无日志
- 检查带 `[NETWORK_RETRYABLE]` 标记的 `error` 任务并自动重启

这部分已经做过性能优化：

- 使用单次查询获取需要检查的任务
- 把创建时间窗口压到 SQL 层

修改看门狗时要避免：

- 扫描全表
- 不加时间窗口地反复处理历史失败任务
- 触发无限重启循环

## 配置系统

### 配置源

- 环境变量
- `.env`
- `.env.{APP_ENV}`
- 数据库中的 `SystemConfig`

### 配置访问

统一通过：

`app/services/config_manager.py`

不要在业务代码里散落地直接读取环境变量，尤其是运行时配置。已有代码绝大多数通过 `get_config_manager()` 或 `TaskManager._get_config()` 获取。

### config_manager 的类型与缓存规则（2026-08 重构后）

- **类型往返**：写入时字符串原样入库，bool/None/数字/容器统一 `json.dumps`；读取时对字符串先尝试 `json.loads`，并对历史 `str(True)/str(False)/str(None)` 产物（`"True"/"False"/"None"`）做兼容还原。因此 `get_config` 对布尔配置返回真正的 `bool`，不要自己写 `== 'true'` 之类的字符串判断。
- **布尔解析统一入口**：`config_manager.coerce_bool(value, default)`。新增布尔配置消费方一律用它，不要再造 `.lower() in (...)` 局部解析（历史上曾有 7-8 种写法并存）。
- **负缓存**：数据库中确认不存在的 key 会以哨兵缓存，后续 `get_config` 直接返回 default、不再查库。注意这意味着运行期新插入的 `SystemConfig` 行（绕过 `set_config` 直接 ORM 写入）在本进程内可能读不到，写配置必须走 `set_config`/`update_configs` 或写后 `refresh_cache()`。
- **线程安全**：`_cache` 由 `RLock` 保护；`_load_configs` 持锁执行。任务线程、看门狗线程、请求线程并发调用是安全的。
- **`get_all_configs()` / `get_google_sheet_config()` 默认读缓存**，不再每次全表刷新；需要强一致的管理端入口显式传 `force_refresh=True`。不要在任务参数循环内反复调用这两个方法（每次都是全量字典拷贝）。
- **日志脱敏**：key 含 `token/secret/password/credential/apikey` 的配置值在日志中打码；`set_config` 的 INFO 日志只记 key。新增敏感配置时沿用该命名约定即可被自动打码。

## 数据模型

`app/models.py`

关键模型：

- `Task`
- `TaskLog`
- `TaskResult`
- `TaskResultReturn`
- `TaskTemplate`
- `SystemConfig`
- `GoogleSheetToken`
- `GoogleSheet`
- `ScheduledTask`

重要字段：

### `Task`

- `status`
- `task_type`
- `config`
- `current_step`
- `total_steps`
- `start_time`
- `end_time`
- `error_message`
- `created_at`

其中：

- `config` 是任务恢复、重启、前端回填的核心
- `error_message` 现在同时承担“用户可见错误摘要”和“看门狗自动恢复信号”的作用

因此不要随意覆盖成无结构的长 traceback。

## 文档编写建议

当你更新这个仓库时，`AGENTS.md` 应优先记录：

- 真正的入口文件和启动钩子
- 实际执行链路
- 容易踩坑的状态同步问题
- 最近引入的重要恢复机制

不要把它写成泛泛的 Flask 教程，也不要复制 README 的营销式描述。

## 在本仓库工作时的具体建议

### 1. 改任务参数时

至少检查四层：

- 页面字段
- 页面回填 / localStorage / 模板恢复
- `task_manager` 子任务透传
- 最终执行 service 消费

### 2. 改异常处理时

优先保留原始异常链，不要写 `raise e`。

推荐：

```python
raise
```

如果需要记录任务级错误摘要，使用统一工具：

- `app/utils/task_error_utils.py`

### 3. 改 Google Sheet 网络逻辑时

优先改：

- `google_sheet_client.py`

其次才是：

- `google_sheet_service*.py`
- `task_manager.py`
- `task_watchdog.py`

### 4. 改看门狗时

优先把筛选条件压到 SQL 层，避免在 Python 层扫大量无关任务。

### 5. 改模板页面时

如果页面里有内联 JS 动态重建 DOM，必须同步更新动态片段，否则刷新后会“变回旧字段”。

## 当前已知重要实现细节

- C31 页面目前把市场值传成英文：
  - `A股 -> cn`
  - `美股 -> en`
- C31 日期字段已经统一命名为 `end_date`
- C31 子任务会在 `task_manager.py` 中透传 `market_type` 与 `end_date`
- `google_sheet_service.py` 的 `cell_kline_data()` 会优先使用 `config.end_date`，未传时走默认逻辑
- 网络异常任务会带 `[NETWORK_RETRYABLE]` 前缀，供看门狗识别
- `TaskManager` 生产实现已经迁移到 `app/services/task/facade.py` + `app/services/task/*`
- backtest 搜索接口位于 `app/routes/backtest_training.py` 的 `search_stocks()`
- 东方财富 K 线代理开关来自 `SystemConfig.dfcf_kline_proxy_enabled`
- K 线字段标准命名（全项目统一英文 schema，无兼容层）：
  - K 线数据行统一使用：`open` 开盘、`high` 最高、`low` 最低、`close` 收盘、`volume` 成交量、`amount` 成交额、`vwap` 加权平均价；`stock_date`/`stock_code`/`stock_name` 保留。所有消费 K 线的代码直接读这些字段。
  - 推送远程的 wire 字段名保持不变：内置库读写（stock_sdk）的 `stock_open`/`stock_max`/`stock_min`/`stock_close`/`stock_volume`/`stock_volume_price`/`stock_limit`/`stock_limit_price`，以及 `db_stock_api.py` payload 键；`KlineService.read_internal_kline_data`/`write_internal_kline_data` 负责两套命名的翻译。
  - 价格类型 `price_mode`（`kp_price`/`sp_price`/`vwap_price`/`ohlc_price`，C7 另有 `random_price`）到价格字段的映射唯一入口是 `app/services/kline_service.py` 的 `get_kline_price_field()`；按价格取序列统一走 `KlineService.build_price_rows()`（取价 + 年份/区间过滤 + 投影 stock_val，可选 OHLC/随机价），不要在 service 里再写取价/投影包装；未知 price_mode 兜底 `vwap`。
  - C4 不走 price_mode，固定按市场取价（A股 `open`、美股 `close`），通过 `build_price_rows(price_field=...)` 直传字段。
  - C7 的 `random_price` 在 `_expand_random_price_groups` 里按 `random_price_range` 分组取随机值（`high_low` 在 low~high 间随机，`open_close` 在 open~close 间随机），随机种子按任务+股票+分组固定，保证可复现。

## 不要做的事

- 不要只改模板不改 JS 回填逻辑
- 不要只改 C31 前端不改 `TaskManager.batch_create_and_start_task()`
- 不要在任务线程里吞掉异常但不写 `Task.error_message`
- 不要把所有失败任务都交给看门狗自动重启
- 不要用 `raise e`
- 不要默认相信 PowerShell 读中文文件不会乱码
- 不要继续把旧 `app/services/task_manager.py` 当成真实生产入口
- 不要把代理账号、密码、token 等敏感信息继续硬编码扩散到仓库里
- 不要随意清除注释的代码和文字详细，只修改上下文需要改动的代码

## svg保存位置
.\docs\design 下建立独立的目录存放
