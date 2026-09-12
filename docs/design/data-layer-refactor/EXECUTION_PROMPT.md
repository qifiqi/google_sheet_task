# 数据层重构 · 执行提示词（目标模式入口）

> 本文件是 `docs/design/data-layer-refactor/` 六份设计文档的执行摘要，可直接整段复制给执行代理作为目标提示词。冲突裁决顺序：本提示词红线 > 六份文档 > 实际调用点代码。

---

你是在 `C:\Users\fuqing\Desktop\google_sheet_task` 仓库（Flask 长时任务执行平台，dev_vue 分支）执行**数据层重构**的代理。完整设计已定稿于 `docs/design/data-layer-refactor/`，共 6 份文档：

- `README.md` —— 背景、目标、核心设计决策
- `01-db-inventory.md` —— 全量清点（文件 → 模型 → ORM 点数 → 目标 repository → 批次）
- `02-repository-design.md` —— base 约定 + 14 个 repository 方法契约
- `03-execution-checklist.md` —— 执行清单（批次、验证命令、回滚、执行记录表）
- `04-exception-response-design.md` —— 统一异常体系与统一响应格式
- `05-task-runtime-pooling.md` —— P1-2 任务执行池化与类型注册表

## 第 0 步（强制）

开工前通读上述 6 份文档；每批动手前重读 `01`（该批文件清点）与 `02`（方法契约）。行号若有偏移以实际代码为准；文档与代码冲突时，以调用点实际代码为契约反向补齐 repository 方法（不得改变调用方行为），并把偏差登记到 `03` 文末"执行记录"表。注意：仓库含大量中文，PowerShell 读写文件显式 UTF-8。

## 目标

1. `routes/` + `services/` 的全部 ORM 操作收敛到 `app/repositories/`，终验 `grep -rEn "db\.session|\.query\." app/routes app/services --include="*.py"` 输出为空（无白名单）；
2. 分层单向：routes（HTTP 编排）→ services（业务编排）→ repositories（独占 ORM）→ models；
3. 全库唯一响应信封 `{status, code, message, data}` + 唯一异常体系（`app/exceptions/`）+ 全局 errorhandler（`app/errors.py`，仅 `/api` 路径返回 JSON，页面路由保持 Flask 默认）;
4. `/api/results*` 三接口从 `template_api.py` 归位到新文件 `routes/result_api.py`，URL 不变。

## 红线（任何批次不得违反）

- 不改 URL、请求结构、HTTP 状态码；响应体原顶层业务键整体移入 `data`（键名不变），**前端读取与 integration 断言同批更新**；
- 不改事务粒度：写方法默认方法内 commit（断点续跑语义），签名带 `commit: bool = True`；异常 `_rollback()` 后裸 `raise`（禁止 `raise e`）；读方法绝不 commit；跨 repository 原子流程用 `base.transaction()` 包裹、各步骤传 `commit=False`（唯一已知场景：auth_api 删用户清 `user_roles` + `Task.created_by_user_id`）;
- **不涉及任何数据库修改**：不改 schema、不写迁移、不动表数据，全部变更仅限代码；
- **无兼容层**：不留旧格式分支、无灰度/回退开关、无双轨 API，每批一次切换到位，合入后代码只存在统一后的形态；
- repositories 禁止 import `app.services` / `app.routes` / Flask（request/jsonify）；routes/services 禁 ORM，但从 `app.models` import 枚举常量（TaskStatus/TaskType 等）允许；
- 任务线程域异常（`C5*`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]` 前缀）**不并入**统一异常体系，保持现状；
- 范围外不动：`app/startup.py`、`run.py`、`app/navigation.py`、`migrations/`、`tests/`、`scripts/`、`app/utils/db_monitor.py`、`db_optimizer.py`；`app/utils/database.py` 在调用点清零后标记 deprecated；
- 每批一个 git commit，**全量 `pytest` 通过才进下一批**。

## 关键契约速记

- 命名：`get_`（可 None）/ `get_required_`（抛 `NotFoundError`）/ `list_` / `count_` / `exists_` / `create_` / `update_` / `delete_` / `bulk_` / `delete_older_than_`；
- 读路径返回 JSON 兼容原生结构（`to_dict()` / with_entities 投影），**信封不下沉数据层**；`get_entity()` 仅任务执行域（runtime 线程目标）使用，长期保留；
- `SystemConfig` 写路径：repository 只管行级读写；负缓存刷新留在 `config_manager` 层（方向 config_manager → repository，禁止反向 import）；
- `api_response` 唯一响应出口三函数：`success(data, message, http_status)` / `error(message, code=None, http_status=400)`（code 默认=http_status）/ `paginated(items, total, page, per_page)`（data={items,total,pages,current_page,per_page}）；routes 禁止手写 `{"status": "error", ...}`；
- 请求校验：`app/utils/request_validation.py` 的 `validate_body(required, types)` / `require_query(name, default, cast)`，失败抛 `ValidationError` → 全局处理器 → 400，路由内不再手写参数错误分支；
- 全局 errorhandler 三层：`AppException`（按 log_level 记日志，detail 仅入日志）→ `HTTPException`（仅 API 路径转 envelope，非 API 保持 Flask 默认）→ 兜底 `Exception`（500 "服务器内部错误"，绝不 str(e) 下发；sqlalchemy.IntegrityError 兜底映射 409）；
- 异常抛出分工：repositories 只抛 `NotFoundError` / `ConflictError`（其他原样上抛）；services 抛语义/业务子类；routes 原则上不 catch。

## 执行顺序（每批详见 03 文档）

1. **P1-3**（独立小改，最先做）：`app/config.py` `_build_engine_options()` MySQL 分支补 `pool_size=10` / `max_overflow=20` / `pool_timeout=30`（均支持环境变量覆盖），SQLite 分支不动。验证：默认值冒烟 + `.env` 覆盖生效。
2. **B0**（纯新增，不改现有行为）：`app/repositories/` 全部 14 文件（契约见 02）+ `app/exceptions/base.py`（AppException 层级：BadRequest/Validation/Unauthorized/Forbidden/NotFound/Conflict/RateLimit/Service）+ `app/errors.py`（`create_app()` 末尾注册）+ 重写 `app/utils/api_response.py`（**同批迁移其仅有的两个消费方 `meta_api.py` / `auth_api.py`，仅响应调用，ORM 不动**）+ `app/utils/request_validation.py` + `AGENTS.md` 增补"接口规范"章节（P1-1 交付物）。验证：pytest 全绿 + `python -c "from app import create_app; create_app()"` 冒烟；此时无人抛 AppException，行为零变化。
3. **B1** 路由层（每文件四合一：repository 替换 + 删 try/except 样板 + 采用 api_response + 前端读取/集成测试断言同批更新；**2-3 文件一个 commit**；逐文件映射见 01 §1）。要点：`/api/results*` 归位 `result_api.py`；scheduler 5 处 `get_or_404` → `get_required` + NotFoundError→404；admin 用 `summary_counts()`/`recent()`；auth_api 删用户走 `transaction()` 原子组合；`database_api.py`/`stock_api.py` 0 ORM 仅统一响应格式。收尾：routes 的 `db.session|.query` 与手写 `"status": "error"` grep 均为 0。
4. **B2** 常规服务（顺序执行，每文件一验）：config_manager（负缓存刷新留在本层）→ stock_metadata_service → task/results → task/query → task/logs → task/dashboard_query → export_service → backtest_training_api_service → scheduler_service → scheduled_task_worker → google_sheet_token_service → google_sheet_registry_service → task_watchdog。`safe_create/safe_update` 调用点（creation/restart/stock_metadata）随批改调 repository。
5. **B3** 任务执行核心（红线：断点 commit 语义、锁原子性、异常链）。顺序：task/occupancy → task/error_handling → task/creation（去 safe_create）→ task/restart（去 safe_update）→ task/runtime_view → task/data_cleanup（清理窗口条件压 SQL 层）→ **task/runtime 最后**。`backtest_repository` 锁 acquire/release 原子性按现状定形；`RetryableNetworkTaskError` 路径不得受影响。冒烟：创建 → 取消 → 重启 → 看门狗单周期。
6. **B4** 执行链与报表。顺序：google_sheet_service_base → google_sheet_service(C3) → C4 → C5 → C7 → backtest_training_service → strategy_backtest_report_service → backtest_multi_product_service → model_summary_service。`task_log_repository.add` 热路径性能与原直写等价。全绿 + 手动跑一个 C3 任务冒烟。
7. **B5** 外围与收尾：`utils/auth.py`（登录热路径，缓存逻辑留在 auth 层，repository 只给 `list_permission_codes`/`get_user`；401 改抛 `UnauthorizedError`）→ `utils/ding_talk_notifier.py` → `ding_stream_service/task_commands.py`（仓库根目录）→ `utils/database.py` 标记 deprecated → 文档更新（AGENTS.md 任务/数据层章节、docs/架构总览.md、docs/数据库模型.md）。终验 grep 三连（routes+services 无 ORM、routes 无手写 error 信封、`except Exception` 仅极少数有注释理由）+ 手动冒烟（登录/任务创建取消重启/模板 CRUD/配置管理/admin 仪表盘）。
8. **P1-2**（前置：B3 完成）：任务执行池化 + 注册表，按 05 文档四步走（每步独立 commit）：① `app/services/task/registry.py`（`TaskTypeSpec` + `TASK_TYPE_REGISTRY`，runtime if/elif → registry，未注册类型不启动并写 error_message）；② 全局 `ThreadPoolExecutor` + `task_max_workers=8`；③ 分类型上限（`task_concurrency_*`）；④ scheduler 裸线程改统一调度入口。并发上限采用**启动前配额检查**（超限保持 pending，不排队不报错，保住看门狗语义）；`Thread.is_alive()` → `not future.done()`；`task_stop_events` 机制不变。**单一路径，无裸线程回退分支**。验收：N>上限压测只有上限内 running，其余 pending 依次启动；取消/重启/看门狗冒烟；`runtime.py` 内 `threading.Thread` 分发残留为 0。

## 每批完成动作（固定循环）

1. 全量 `pytest`（配置已带 `--basetemp=.pytest_tmp`，直接跑即可）；
2. 按 03 文档执行该批 grep 验证；
3. git commit（单批一提交，出问题 `git revert` 单批回滚；B3/B4 单文件语义风险可单独回退 ORM 版本并在"执行记录"标注豁免）；
4. 在 `03-execution-checklist.md` 文末"执行记录"表登记：日期 / 批次·文件 / 结果 / 偏差说明。

## 新增测试

- `tests/unit/test_repositories.py`：内存 SQLite + app context，覆盖各 repository 基础读写与异常路径（测试代码不受禁 ORM 约束）；
- 每批替换后相关既有 unit/integration 测试全绿。
