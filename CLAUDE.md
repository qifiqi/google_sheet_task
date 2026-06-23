# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本文件用于指导 Claude Code 在本仓库内工作。目标是帮助代理快速理解项目的真实结构、常见风险点和推荐操作方式。

## 项目定位

基于 Flask 的长时间运行任务执行平台，核心能力：Google Sheet 参数批量校验（C3/C4/C5 多模板）、C31 批量拆分、backtest_training 回测训练、任务调度与看门狗、Google Sheet token/sheet 资源占用管理、RBAC 权限控制。

任何修改都要优先考虑：线程生命周期、数据库与内存状态一致性、Token/Sheet 占用释放、失败后可恢复性、网络抖动下的重试和重连。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端 (Flask, port 5000)
python run.py

# 启动前端开发服务器 (Vite, port 3000, 代理 API 到 5000)
cd frontend && npm install && npm run dev

# 构建前端
cd frontend && npm run build

# 数据库迁移
flask db migrate -m "message"
flask db upgrade

# 测试
pytest
pytest tests/test_specific.py::test_name

# Docker 部署
docker-compose up -d
```

### 测试注意事项

- `tests/test/google_sheet_test.py`、`tests/test/token_test.py` 依赖本地 token 文件或外部环境，全量收集失败时不要误判为代码改动引入
- 回归入口：`tests/test/test_p0_p1_refactor.py` 以及与改动直接相关的定向测试
- `tests/conftest.py` 提供 SQLite in-memory 的 app fixture

## 双前端架构

项目同时存在两套前端：

1. **Legacy Jinja2 模板** (`templates/`) — Bootstrap 5 + 内联 JS，服务端渲染
2. **Vue 3 SPA** (`frontend/`) — Vite + Element Plus + Vue Router，开发中

Vue 前端通过 Vite dev server 代理 `/api`、`/admin/api`、`/backtest-training/api` 到 Flask 5000 端口。

## 真实入口与启动流程

### 应用工厂 `app/__init__.py`

`create_app()` → 加载 `.env` + `.env.{APP_ENV}` → 验证 auth 配置 → 初始化 db/migrate → 初始化 config_manager → 注册蓝图 → 注入模板上下文 → 初始化钉钉通知器

### 启动引导 `run.py` + `app/startup.py`

`run.py` 调用 `bootstrap_app(app)` 执行启动期动作：

- `db.create_all()`
- `ensure_google_sheet_token_schema()` / `ensure_user_schema()` / `ensure_task_schema()` — 运行时 ALTER TABLE 补列
- `reset_google_sheet_token_occupancy()` / `reset_google_sheet_occupancy()`
- `init_config2()` — 种子默认 SystemConfig
- `init_rbac()` — 初始化角色/权限/默认管理员
- `init_navigation_menu()` — 初始化导航菜单
- `check_and_cleanup_dead_tasks()`
- `init_scheduler()` / `init_task_watchdog()`

任何影响任务状态、token 占用、RBAC、用户字段、看门狗行为的修改，都要同时评估 `run.py` 和 `app/startup.py`。

## 任务系统核心

### 任务主控门面（Facade Pattern）

生产实现位于 `app/services/task/`，对外仍暴露 `TaskManager` / `task_manager`：

- `app/services/task/facade.py` — 门面入口
- `app/services/task/runtime.py` — `start_task()`, `_execute_*_task()`
- `app/services/task/creation.py` — `create_task()`, `batch_create_and_start_task()`
- `app/services/task/restart.py` — `cancel_task()`, `restart_task()`
- `app/services/task/occupancy.py` — Token/Sheet 占用管理
- `app/services/task/query.py` — 任务查询
- `app/services/task/results.py` — 结果处理

运行态数据结构：`running_tasks` (task_id→thread), `task_stop_events` (task_id→Event), `task_token_occupancy`

> 旧 `app/services/task_manager.py` 如果还存在只是兼容层，不是生产入口。

### C31 特殊逻辑

C31 不是独立执行器，是前端批量创建页。最终在 `batch_create_and_start_task()` 中拆成多个 C3 子任务。新增字段需要三层透传：前端 config → `batch_create_and_start_task()` child_config → `google_sheet_service.py` 消费。

## Google Sheet 执行链路

### 网络层 `app/services/google_sheet_client.py`

基于 gspread + google.oauth2，包含：timeout、代理注入、网络重试、重连、`RetryableNetworkTaskError` 抛出。网络问题优先改这里。

### 业务服务

- `app/services/google_sheet_service.py` — C3
- `app/services/google_sheet_service_C4.py`
- `app/services/google_sheet_service_C5.py`
- `app/services/backtest_training_service.py`
- `app/services/backtest_multi_product_service.py`

共同模式：`execute_task()` 加载配置 → 初始化连接 → 逐步执行参数组合 → 保存 TaskResult/TaskLog → 支持取消和断点恢复。全部在后台线程运行。

### 东方财富/股票 API

- `app/utils/dfcf_api.py` — 股票搜索（codetable 优先，suggest 回退）、K 线拉取
- `app/utils/proxy_manager.py` — 代理管理
- K 线代理开关：`SystemConfig.dfcf_kline_proxy_enabled`

## 看门狗 `app/services/task_watchdog.py`

- 检查最近 5 天创建的任务
- 检查 `running` 任务是否长时间无日志
- 自动重启带 `[NETWORK_RETRYABLE]` 标记的 `error` 任务
- 筛选条件已压到 SQL 层，避免全表扫描

## 配置系统

配置源优先级：环境变量 → `.env` → `.env.{APP_ENV}` → 数据库 `SystemConfig`

统一通过 `app/services/config_manager.py` 的 `get_config_manager()` 访问，不要在业务代码里散落地直接读取环境变量。

关键环境变量：`APP_ENV`, `DATABASE_URL`, `SECRET_KEY`, `AUTH_ENABLED`, `JWT_SECRET_KEY`

## RBAC 与鉴权

- 模型：`User`, `Role`, `Permission`（多对多关联表）
- 装饰器：`@login_required`, `@permission_required(...)`
- JWT：access_token + refresh_token，`token_version` 实现单点登录
- 默认管理员：admin / admin123
- 权限定义在 `app/config.py` 的 `PERMISSIONS` 列表（42 个权限，9 组）

## 数据模型 `app/models.py`

关键模型：Task, TaskLog, TaskResult, TaskResultReturn, TaskTemplate, SystemConfig, GoogleSheetToken, GoogleSheet, ScheduledTask, User, Role, Permission, NavigationMenuItem

`Task.config` 是任务恢复/重启/前端回填的核心。`Task.error_message` 同时承担用户可见错误摘要和看门狗自动恢复信号，不要随意覆盖成无结构的长 traceback。

## 在本仓库工作时的具体建议

### 改任务参数时

至少检查四层：页面字段 → 页面回填/localStorage/模板恢复 → `task/creation.py` 子任务透传 → 最终执行 service 消费

### 改异常处理时

保留原始异常链，用 `raise` 而非 `raise e`。记录任务级错误摘要使用 `app/utils/task_error_utils.py`。

### 改 Google Sheet 网络逻辑时

优先改 `google_sheet_client.py`，其次 `google_sheet_service*.py`，最后 `task/runtime.py` 或 `task_watchdog.py`。

### 改看门狗时

优先把筛选条件压到 SQL 层，避免 Python 层扫大量无关任务。避免触发无限重启循环。

### 改模板页面时

内联 JS 动态重建 DOM 的页面，必须同步更新动态片段，否则刷新后会"变回旧字段"。

## 当前已知重要实现细节

- C31 市场值映射：`A股 → cn`, `美股 → en`
- C31 日期字段统一命名 `end_date`
- C31 子任务透传 `market_type` 与 `end_date`
- `google_sheet_service.py` 的 `cell_kline_data()` 优先使用 `config.end_date`
- 网络异常任务带 `[NETWORK_RETRYABLE]` 前缀供看门狗识别
- backtest 搜索接口位于 `app/routes/backtest_training.py` 的 `search_stocks()`
- 启动时 schema 修补在 `app/startup.py`，不完全依赖 Alembic 迁移

## 不要做的事

- 不要只改模板不改 JS 回填逻辑
- 不要只改 C31 前端不改 `batch_create_and_start_task()`
- 不要在任务线程里吞掉异常但不写 `Task.error_message`
- 不要把所有失败任务都交给看门狗自动重启
- 不要用 `raise e`
- 不要把旧 `app/services/task_manager.py` 当成生产入口
- 不要把敏感信息硬编码到仓库里
