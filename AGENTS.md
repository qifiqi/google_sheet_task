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

### 测试

```bash
pytest
pytest tests/test_specific.py::test_name
```

注意：

- 当前仓库里的测试并不全是“开箱即跑”的纯单元测试
- `tests/test/google_sheet_test.py`、`tests/test/token_test.py` 这类文件依赖本地 token 文件或外部环境，`pytest` 全量收集失败时不要第一时间误判为本次代码改动引入
- 更适合作为当前主分支结构回归入口的是：
  - `tests/test/test_p0_p1_refactor.py`
  - 以及与本次改动直接相关的定向测试

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

`run.py` 不是一个薄壳，但启动期修复逻辑现在已经明显下沉到：

- `app/startup.py`

`run.py` 仍然负责串起这些启动动作，核心包括：

- 初始化日志
- `db.create_all()`
- `ensure_google_sheet_token_schema()`
- `ensure_user_schema()`
- `ensure_task_schema()`
- `reset_google_sheet_token_occupancy()`
- `reset_google_sheet_occupancy()`
- `init_config2()`
- `init_rbac()`
- `check_and_cleanup_dead_tasks()`
- `init_scheduler()`
- `init_task_watchdog()`

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

- `tests/legacy_services/task_manager.py` 只是兼容层，不是生产实现
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