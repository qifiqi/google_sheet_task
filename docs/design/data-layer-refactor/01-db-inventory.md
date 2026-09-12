# 01 - 数据库操作全量清点

> 统计口径：`grep -E "db\.session|\.query\."`（含 `Model.query` / `db.session.get/add/delete/execute/flush`）。
> 清点日期：2026-09-04，基于 dev_vue 分支工作区。执行替换时若发现行号偏移，以调用点实际代码为准；模型归属与批次不变。

## 1. 路由层（批次 B1）

| 文件 | ORM 点 | commit 点 | 触达模型 | 目标 repository | 备注 |
|---|---|---|---|---|---|
| `routes/auth_api.py` | 35 | 10 | User, Role, Permission, user_roles, role_permissions, Task, NavigationMenuItem | rbac_repository, task_repository | 用户/角色全套 CRUD + 关联表 `db.session.execute(delete)`；删用户时同事务清 `Task.created_by_user_id`（用 transaction() 保持原子） |
| `routes/template_api.py` | 19 | 4 | TaskTemplate, Task, TaskResult | task_template_repository, task_repository, task_result_repository | `/api/results*` 三个接口归位到新文件 `routes/result_api.py`（URL 不变），与模板接口解耦 |
| `routes/config_api.py` | 19 | 4 | SystemConfig, NavigationMenuItem | system_config_repository, navigation_repository | 导航菜单 CRUD 含 flush 取 id（create 带 flush 语义）；`/config` POST 走 config_manager（保持缓存语义） |
| `routes/scheduler_api.py` | 18 | 4 | ScheduledTask | scheduled_task_repository | 5 处 `get_or_404` → `get_required_scheduled_task` + NotFoundError→404 映射 |
| `routes/google_sheet_api.py` | 7 | 1 | GoogleSheetToken, GoogleSheet | google_sheet_token_repository, google_sheet_repository | 增删改查 + token 导入 |
| `routes/admin.py` | 7 | 0 | Task | task_repository | 首页仪表盘计数（22-29 行）+ runtime-detail + model-summary rebuild；`db.session.get(Task, id)` 视消费方式选 `get`（dict）或 `get_entity` |
| `routes/backtest_multi_product.py` | 5 | 1 | Task, TaskResult, TaskResultReturn | task_repository, task_result_repository | |
| `routes/task_api.py` | 4 | 0 | Task, TaskResult | task_repository, task_result_repository | `_get_task_or_404`（db.session.get）、distinct task_type、批量导出 `Task.id.in_`、364 行聚合查询 |
| `routes/backtest_training.py` | 2 | 0 | Task, TaskResult, TaskResultReturn | task_repository, task_result_repository | |
| `routes/export_api.py` | 2 | 0 | Task, TaskResult | task_repository, task_result_repository | |
| `routes/google_sheet.py` | 1 | 0 | Task, TaskTemplate | task_repository, task_template_repository | 页面路由 |
| `routes/global_preview.py` | 1 | 0 | Task | task_repository | |
| `routes/yule.py` | 0 | 0 | (import TaskTemplate) | task_template_repository | 无 ORM 调用；替换时顺带核对 import 是否可去除 |
| `routes/meta_api.py` | 0 | 0 | (import 枚举) | — | 仅枚举常量引用；响应已随 B0 切统一信封 |
| `routes/database_api.py` | 0 | 0 | （无 ORM，走 db_monitor/db_optimizer） | — | 手写旧格式响应 7 处，B1 仅统一响应格式 |
| `routes/stock_api.py` | 0 | 0 | （无 ORM） | — | 手写旧格式响应 3 处，B1 仅统一响应格式 |
| `routes/auth_pages.py` / `eastmoney_kline.py` / `xpl.py` | 0 | 0 | （无 ORM、无手写信封） | — | 无需替换 |

路由层合计：**120 ORM 点 / 24 commit 点**（2026-09-04 实测复核，行数口径）。

## 2. 服务层（批次 B2 / B3 / B4）

### B2 —— 常规服务（非任务执行核心线程）

| 文件 | ORM 点 | commit 点 | 触达模型 | 目标 repository |
|---|---|---|---|---|
| `services/google_sheet_token_service.py` | 27 | 5 | GoogleSheetToken, Task | google_sheet_token_repository, task_repository |
| `services/model_summary_service.py` | 33 | 6 | Task, TaskLog, TaskResult, TaskResultSummaryIndex | task/log/result/backtest_repository |
| `services/scheduler_service.py` | 21 | 7 | ScheduledTask, TaskLog, TaskResult | scheduled_task/log/result_repository |
| `services/task_watchdog.py` | 17 | 5 | Task, TaskLog | task_repository, task_log_repository |
| `services/google_sheet_registry_service.py` | 15 | 6 | GoogleSheet | google_sheet_repository |
| `services/scheduled_task_worker.py` | 12 | 4 | ScheduledTask, TaskLog, TaskResult | scheduled_task/log/result_repository |
| `services/backtest_training_api_service.py` | 9 | 0 | Task, TaskResult, TaskResultReturn | task/result_repository |
| `services/task/logs.py` | 8 | 3 | TaskLog | task_log_repository |
| `services/config_manager.py` | 8 | 2 | SystemConfig | system_config_repository |
| `services/task/dashboard_query.py` | 7 | 0 | Task | task_repository |
| `services/stock_metadata_service.py` | 4 | 0 | StockMetadata | stock_metadata_repository |
| `services/export_service.py` | 4 | 0 | Task, TaskResult | task/result_repository |
| `services/task/query.py` | 3 | 0 | Task, TaskResult | task/result_repository |
| `services/task/results.py` | 1 | 0 | TaskResult | task_result_repository |
| `services/stock_search_service.py` | 1 | 1 | (StockMetadata 写入) | stock_metadata_repository |

### B3 —— 任务执行核心（线程语义，最后替换 `task/runtime.py`）

| 文件 | ORM 点 | commit 点 | 触达模型 | 目标 repository | 红线 |
|---|---|---|---|---|---|
| `services/task/data_cleanup.py` | 9 | 0 | TaskLog, TaskResult, TaskResultReturn, TaskResultSummaryIndex, BacktestSheetRunLock | log/result/backtest_repository | 清理窗口条件必须压在 repository 的 SQL 层 |
| `services/task/restart.py` | 10 | 4 | Task（+ utils.database safe_update） | task_repository | 同时移除 `safe_update` 依赖 |
| `services/task/creation.py` | 6 | 2 | Task（+ utils.database safe_create） | task_repository | 同时移除 `safe_create` 依赖 |
| `services/task/runtime_view.py` | 5 | 0 | Task, TaskLog, TaskResult, TaskResultReturn | task/log/result_repository | |
| `services/task/error_handling.py` | 4 | 1 | Task, TaskLog | task/log_repository | |
| `services/task/occupancy.py` | 4 | 0 | GoogleSheet, Task | google_sheet_repository, task_repository | 占用/释放与 token 状态的原子性 |
| `services/task/runtime.py` | 33 | 12 | Task, BacktestSheetRunLock | task_repository, backtest_repository | **最后替换**；每步 commit、锁 acquire/release 原子性、`RetryableNetworkTaskError` 路径不得受影响 |

### B4 —— 执行链与报表服务

| 文件 | ORM 点 | commit 点 | 触达模型 | 目标 repository |
|---|---|---|---|---|
| `services/google_sheet_service.py` | 13 | 1 | Task, TaskResult, TaskResultReturn | task/result_repository |
| `services/google_sheet_service_C4.py` | 12 | 1 | 同上 | 同上 |
| `services/google_sheet_service_C5.py` | 13 | 1 | 同上 | 同上 |
| `services/google_sheet_service_C7.py` | 13 | 1 | 同上 | 同上 |
| `services/google_sheet_service_base.py` | 4 | 1 | Task, TaskLog | task/log_repository |
| `services/backtest_training_service.py` | 13 | 1 | Task, TaskResult, TaskResultReturn | task/result_repository |
| `services/backtest_multi_product_service.py` | 20 | 2 | Task, TaskResult, TaskResultReturn, BacktestProductResultCache | task/result/backtest_repository |
| `services/strategy_backtest_report_service.py` | 3 | 0 | TaskResult, TaskResultReturn | task_result_repository |
| `services/model_summary_service.py` | （见 B2，因体量与 SummaryIndex 耦合，允许排入 B4执行） | | | |

服务层合计：**332 ORM 点 / 66 commit 点**（2026-09-04 实测复核，行数口径）。

## 3. 外围与工具（批次 B5）

| 文件 | ORM 点 | 触达模型 | 目标 repository | 备注 |
|---|---|---|---|---|
| `utils/auth.py` | 2 | User, Permission | rbac_repository | **登录热路径**：`Permission.query.all()`（权限缓存填充）、`db.session.get(User, id)`；缓存逻辑留在 auth 层，repository 只提供 list_permission_codes / get_user |
| `utils/ding_talk_notifier.py` | 2 | User, Task | rbac_repository, task_repository | 值班用户列表 + 任务读取 |
| `ding_stream_service/task_commands.py`（**仓库根目录**，非 `app/` 下） | 4 | Task | task_repository | 钉钉流式命令服务 |

## 4. 明确不动清单（范围外）

| 位置 | ORM 点 | 不动理由 |
|---|---|---|
| `app/startup.py`、`run.py` | 若干 | bootstrap：schema 修补、资源恢复、死任务重置、幂等播种（用户指定剔除） |
| `app/navigation.py` | 2 | RBAC/导航初始化播种，属启动期 |
| `app/config.py` | 1 | 框架配置默认值注册时读 SystemConfig 元数据；启动期，B5 结束后可评估 |
| `app/utils/db_monitor.py` | 19 | 运维诊断工具，仅 `database_api.py` 使用，保留 |
| `app/utils/db_optimizer.py` | 16 | 运维工具，app 内无调用方，保留 |
| `app/utils/database.py` | 22 | 泛型 safe_* helper。**其调用点**（task/creation、task/restart、stock_metadata_service）在 B2/B3 改调 repository；全部替换后本文件标记 deprecated |
| `app/utils/db_retry.py` | 0 | 网络重试装饰器，非 ORM，保留 |
| `migrations/`、`tests/`、`scripts/`、`tests/scripts/`、`tests/test/` | — | 不在业务范围 |
| `ding_stream_service/`（仓库根目录）其余文件 | 0 | 无 ORM |

## 5. 收尾验收口径

替换全部完成后，以下命令输出必须为空（无任何例外白名单）：

```bash
grep -rEn "db\.session|\.query\." app/routes app/services --include="*.py"
```

`app/models` 的直接 import 仅允许枚举常量（`TaskStatus`/`TaskType`/`TaskResultType`/`GoogleSheetTokenTaskType`/`GoogleSheetTableType`/`TaskStatus` 等）。
