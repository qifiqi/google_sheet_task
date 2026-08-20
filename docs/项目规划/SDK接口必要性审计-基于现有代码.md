# SDK 接口必要性审计（基于现有代码）

> 日期：2026-08-19  
> 范围：以当前 Flask 实现、`app/models.py` 的约束、已生成的 `stock_sdk` CRUD 为依据。  
> 目的：只保留“去掉本地数据库直连后仍无法由业务层正确完成”的远程接口需求。

## 1. 判定规则

| 结论 | 含义 |
| --- | --- |
| **不新增接口** | 业务层可调用现有 `GetInfoById` / `GetDataByPageList` / `ModifyOrAdd` / `Delete`，并由远程数据库已有唯一约束最终保证正确性。 |
| **仅需远程数据约束** | 不需要新 HTTP Action，但远程数据表必须保留/补齐唯一约束，并将冲突稳定返回给 SDK。 |
| **单实例可业务编排** | 当前单 Flask 进程、单调度器部署可通过进程内 `threading.Lock` + 已有 CRUD 完成；多实例部署时该方案失效。 |
| **必须新增接口** | 现有 CRUD 无法表达必要筛选，或读取后更新会造成跨实例的数据竞争，或需要远程资源中不存在的数据模型。 |

**当前项目可先按单 Flask worker 运行。** `app/startup.py` 已明确调度器和看门狗是进程内组件，多 worker/多副本会产生重复巡检。因此“单实例可业务编排”符合当前运行模型，但不是未来横向扩容的方案。

## 2. 最终结论

当前全量去除业务代码中的 ORM 直连，严格必需的新远程能力仅有：

| 必要级别 | 接口/资源 | 现有代码依据 | 原因 |
| --- | --- | --- | --- |
| 必须 | `ParamTasks/Query` | `TaskQueryService.get_tasks_paginated()` 按类型、状态、关键字分页并返回统计 | SDK 分页 DTO 只有页码和排序，不能正确完成任务列表筛选和总数/统计。 |
| 必须 | `ParamTaskLogs/Query` | `TaskLogMixin.get_task_logs()` 需要 `task_id`、时间倒序、limit | SDK 不能按 `task_id` 筛选；全量日志分页后再过滤不正确。 |
| 必须 | `ParamTaskResults/Query` | 结果页、回测详情、导出、全局预览都按 `task_id`、步骤、成功状态取结果 | SDK 不能按 `task_id` 筛选，且结果 JSON 很大，不能客户端扫全表。 |
| 必须 | `ParamTaskResultsReturn/Query` | 回测收益序列按 `task_id` 读取 | 同上。 |
| 必须 | `ParamStockMetadata/QueryByBusinessKey` | `StockMetadata` 唯一键为 `stock_code + market_type` | SDK 只能按 ID 读；代码需要按业务键查缓存记录。 |
| 必须 | `ParamBacktestProductResultCache/QueryByBusinessKey` | 多品回测以 `batch_id + cache_key` 判定缓存命中 | SDK 只能按 ID 读；唯一冲突后必须能精确重读先成功者的数据。 |
| 必须 | `ParamGoogleSheetTokens/Query` | Token 按 `task_type`、启用状态、容量筛选 | SDK 列表无筛选，当前代码已拒绝走全量远程筛选。 |
| 必须 | `Identity` / `AccessControl` / `NavigationMenu` | 本地 `User`、`Role`、`Permission`、`NavigationMenuItem` 无 SDK 等价模型 | 没有可复用的远程数据资源；`sys_user/sys_role` 字段和鉴权语义不一致。 |

若继续保持单实例部署，**无需为了锁、Sheet 占用、缓存 Upsert、索引 Upsert、任务批量写入、调度任务状态而新增 HTTP Action**。对应业务层实现及所需数据约束见后文。

## 3. 不需要新增接口：现有 CRUD + 业务约束即可

### 3.1 Google Sheet 注册表

| 操作 | 业务层做法 | 远程数据保证 | 结论 |
| --- | --- | --- | --- |
| 新增 | 校验 `spreadsheet_id`、规范化 `table_type`、计算 `registry_scope`，调用 `ModifyOrAdd` | 已有 `spreadsheet_id + registry_scope` 唯一约束 | 不新增接口 |
| 更新 | `GetInfoById` 后合并允许字段并保存 | 同上 | 不新增接口 |
| 删除 | `GetInfoById` 后执行 `Delete`；业务侧拒绝正在使用的 Sheet | 服务端 `Delete` 应额外拒绝仍存在运行锁的记录 | 不新增 Action；仅需约束 |
| 页面展示 | 使用现有分页接口读取 | 当前注册量很小；超过一页时业务层按页读取并过滤 | 不新增接口；后续规模化再加 Query |

当前 `GoogleSheetRegistryService.create_sheet()` / `update_sheet()` 从远程拉取 `page_size=1000` 并在内存判重，只能作为友好提示，不能作为正确性机制；最终以唯一约束冲突为准。

### 3.2 回测 Google Sheet 运行锁

`BacktestSheetRunLock` 已有 `UNIQUE(spreadsheet_id)`；当前本地实现也采用“插入记录，捕获唯一冲突”的方式。

| 步骤 | 业务层调用 | 约束/异常处理 |
| --- | --- | --- |
| 加锁 | `ModifyOrAdd({id: null, spreadsheet_id, task_id, task_type})` | 成功即持锁；唯一冲突说明其他任务持锁。|
| 可重入 | 已持有时跳过创建；任务配置保存 `lock_id` | 同一任务绝不覆盖其他任务记录。 |
| 解锁 | `GetInfoById(lock_id)`，确认 `task_id` 一致后 `Delete(lock_id)` | 不存在视为已释放；归属不一致禁止删除。 |
| 异常恢复 | 按任务配置的 `lock_id` 尝试删除 | 运维/启动期可分页扫描孤儿锁；不是运行主路径。 |

结论：不需要 `AcquireLease`、`RenewLease`、`ReleaseByTask` 等新接口。前提是远程 `ModifyOrAdd` 的新增请求不能静默覆盖唯一冲突，而要返回可识别的重复键错误。

### 3.3 Google Sheet 任务占用

当前 `GoogleSheet.is_in_use/current_task_id` 与回测锁功能重叠。去除本地 ORM 后，建议不再写这两个易失占用字段：

- 回测任务：统一使用 `BacktestSheetRunLock`。
- 非回测 Google Sheet 任务：当前架构允许并行时不设置互斥；若业务需要互斥，也复用同一锁表（`task_type=google_sheet`）。
- 注册表 `is_in_use/current_task_id` 仅作为页面显示的派生状态：由任务配置或锁记录计算，不作为事实来源。

结论：不新增 `ParamGoogleSheet/AcquireForTask` 与 `ReleaseByTask`。删除/修改 Sheet 时只需业务层检查已知锁；服务端删除仍应防御性检查锁是否存在。

### 3.4 多品回测缓存

`BacktestProductResultCache` 已有 `UNIQUE(batch_id, cache_key)`。

1. 业务层需要缓存时，先调用新增的精确业务键查询接口读取（见第 2 节）。
2. 未命中时，调用已有 `ModifyOrAdd` 新增记录。
3. 并发下若唯一冲突，重新按业务键读取，得到先成功者写入的缓存。

结论：不新增 Upsert 接口；唯一键 + 冲突重读即可。

### 3.5 单模型汇总索引

`TaskResultSummaryIndex` 已有 `UNIQUE(task_result_id, model_key)`。

- Flask 可使用 `ParamTasks/Query` 和 `ParamTaskResults/Query` 分页读取完成任务，计算汇总行后通过 `ModifyOrAdd` 写入。
- 写入冲突时，可保留本次重建批次已生成的 `task_result_id + model_key -> id` 本地映射；下一次重建可先删除该任务的既有索引再重建。因此不要求额外的索引业务键查询接口。
- “每组只保留最优记录”的排序与比较可以放在业务层；现有实现已在 Python 中逐行处理后写库。
- 索引重建作业、进度和 CSV/Excel 渲染均可保留 Flask 进程内实现。

结论：不新增 `Rebuild`、`RefreshForTask`、`UpsertByBusinessKey` 接口；只有需要把重建转移到远程异步 worker 或索引表达到大量数据时才增加。

### 3.6 任务创建、重启、取消、删除及执行写入

| 现有业务 | 业务侧可行实现 | 是否新增 Action |
| --- | --- | --- |
| 创建/创建重启任务 | 生成 UUID，调用 `ParamTasks/ModifyOrAdd`；再启动本地线程 | 否 |
| C31 批量创建 | 顺序调用已有 CRUD；中途失败时按已创建 ID 补偿删除 | 否 |
| 更新配置 | `GetInfoById` → 合并/规范化配置 → `ModifyOrAdd` | 否 |
| 取消 | 内存停止事件 + `GetInfoById` → 设为 `cancelled` → `ModifyOrAdd` | 否（单实例） |
| 重启 | 业务侧重置步骤/错误/时间，按规则清理结果，再 `ModifyOrAdd` | 否（单实例） |
| 删除 | 先删结果、收益、日志、索引、锁，最后删任务；失败记录日志后可重试 | 否（单实例） |
| 执行时写日志/结果/收益 | 每条或按当前服务的批次循环调用 `ModifyOrAdd` | 否 |

这些路径会比本地事务增加远程调用次数，但在当前单实例、小批量任务场景可正确恢复：关联记录均带 `task_id`，清理操作设计成可重复执行即可。是否合并为 `AppendBatch` / `DeleteCascade` 是性能与运维优化，不是功能必需。

### 3.7 系统配置、模板、定时任务

| 资源 | 业务侧实现 | 结论 |
| --- | --- | --- |
| `SystemConfig` | 启动时分页读取并缓存在 `config_manager`；修改时单条 `ModifyOrAdd` | 不新增接口 |
| `TaskTemplate` | 现有 Repository CRUD | 不新增接口 |
| `ScheduledTask` | 单调度实例读取全部启用项；执行前由进程内调度锁保护，更新 `is_running/run_count/last_run_time` 使用 `ModifyOrAdd` | 不新增接口（当前单实例） |

## 4. 仍然必须新增的查询接口

### 4.1 `ParamTasks/Query`

请求条件：`page_index`、`page_size`、`task_types`、`statuses`、`keyword`、`created_from`、`created_to`、`sort`、`include_statistics`。

必须原因：当前 `get_tasks_paginated()` 需要服务端按任务类型、状态、名称/描述/ID 关键字筛选，并在筛选集上统计 `total/completed/running/error/pending/today_new/平均耗时`。基础分页无法正确替代。

### 4.2 `ParamTaskLogs/Query`

请求条件：`task_id`、`levels`、`timestamp_from`、`timestamp_to`、`limit`、`after_id`、`sort`。

必须原因：任务日志读取是运行与状态检查主路径，基础分页不能用 `task_id` 下推筛选。

### 4.3 `ParamTaskResults/Query`

请求条件：`task_id`（普通页面必填；保留期清理时省略）、`ids`、`step_index_from`、`step_index_to`、`success`、`timestamp_from`、`timestamp_to`、`fields`、分页/排序、`include_counts`。

必须原因：结果页面、全局预览、导出、恢复都依赖按任务范围读取。`fields` 是必需的投影能力，普通列表不能返回所有大 JSON。

### 4.4 `ParamTaskResultsReturn/Query`

请求条件：`task_id`、`stock_date_from`、`stock_date_to`、`ids`、`fields`、分页/排序。

必须原因：收益序列必须按任务范围检索，不能扫描全表。

### 4.5 `ParamStockMetadata/QueryByBusinessKey`

请求条件：`stock_code`、`market_type`。

必须原因：`stock_code + market_type` 是代码当前实际使用的唯一业务键；基础 CRUD 仅支持 ID。

### 4.6 `ParamGoogleSheetTokens/Query`

请求条件：`task_types`、`is_active`、`available_only`、`token_ids`、`name_keyword`、分页/排序；默认不返回 `token_context`。

必须原因：Token 选择和展示需按任务类型/可用状态下推筛选。服务端须保持敏感字段脱敏。

### 4.7 `ParamBacktestProductResultCache/QueryByBusinessKey`

请求条件：`batch_id`、`cache_key`。

必须原因：缓存读取和唯一冲突后的恢复都要精确定位记录，基础 CRUD 只支持按主键读取。

## 5. 条件性必需：只有多实例部署时新增

| 接口 | 当前为何不需要 | 何时必须新增 |
| --- | --- | --- |
| `ParamTasks/CompareAndSetStatus` | 当前线程注册表阻止本进程重复启动，业务层可串行读写 | 多 Flask worker / 多副本同时启动、取消、重启同一任务 |
| `ParamGoogleSheetTokens/Reserve` / `ReleaseByTask` | 单实例可用进程内锁将 Token 选择、计数递增、写回串行化 | 多实例共享 Token 池、必须保证全局上限 |
| `ParamBacktestSheetRunLocks/AcquireLease` / `RenewLease` | 已有锁表唯一键 + CRUD 能保证互斥 | 需要自动过期、持锁进程可能长期失联、需锁续期 |
| `ParamScheduledTasks/ClaimRun` / `CompleteRun` | 当前调度器约定为单实例 | 多个 scheduler 实例执行同一数据库任务 |
| `ParamTasks/DeleteCascade` / `AppendBatch` | 业务侧可用 task_id 幂等补偿 | HTTP 往返过多、需要跨资源全有或全无的强事务 |

## 6. 必须由远程服务保留的数据库约束

这些不是新增 HTTP 接口，却是业务侧方案成立的前提：

| 表 | 约束 | 用途 |
| --- | --- | --- |
| `t_param_google_sheet` | `UNIQUE(spreadsheet_id, registry_scope)` | Sheet 注册去重 |
| `t_param_backtest_sheet_run_locks` | `UNIQUE(spreadsheet_id)` | Sheet 运行锁 |
| `t_param_backtest_product_result_cache` | `UNIQUE(batch_id, cache_key)` | 缓存并发写入时冲突重读 |
| `t_param_stock_metadata` | `UNIQUE(stock_code, market_type)` | 股票元数据唯一性 |
| `t_param_task_result_summary_index` | `UNIQUE(task_result_id, model_key)` | 汇总索引幂等写入 |
| `t_param_tasks` | `PRIMARY KEY(id)` | 任务 UUID 幂等创建与更新 |

远程 API 在上述约束冲突时必须返回可判别的业务错误（建议 `ret_code=409`，并含稳定错误代码，如 `DUPLICATE_KEY`）。不能将冲突伪装为成功，亦不能以“更新同唯一键的其他任务记录”替代错误。

## 7. 迁移时应删除或替换的本地数据库做法

| 当前代码 | 替换方向 |
| --- | --- |
| `GoogleSheetRegistryService` 用 `list_page(page_size=1000)` 本地判重 | 表单校验 + 远程唯一约束冲突映射 |
| `GoogleSheet.is_in_use/current_task_id` 读改写 | 用 `BacktestSheetRunLock` 唯一记录作为占用事实 |
| `BacktestSheetRunLock.query...` 与 `IntegrityError` | SDK `ModifyOrAdd` + 远程 `DUPLICATE_KEY` 错误映射 |
| `TaskResult/TaskLog/TaskResultReturn` 的 `query.filter_by(task_id=...)` | 第 4 节专用 Query 接口 |
| `Task` 本地分页筛选和仪表盘统计 | `ParamTasks/Query` |
| Token 的本地筛选和容量统计 | `ParamGoogleSheetTokens/Query`；单实例下容量更新用业务锁 + CRUD |
| 本地 `db.create_all`、`ensure_*_schema` | 迁移到远程数据服务的 schema migration；Flask 不再执行 DDL |

## 8. 实施验收

1. 任何 `app/routes`、`app/services`、`app/utils` 不再导入 `db` 或业务 ORM Model；仅 Repository/SDK 适配层访问 HTTP。
2. Sheet 重复创建、缓存并发写、汇总重复写、同 Sheet 回测并行启动的定向测试均使用 fake SDK 模拟 `DUPLICATE_KEY`，验证不产生错误覆盖。
3. 单实例测试覆盖：创建、取消、重启、异常恢复、日志、结果、收益序列、导出、调度器与看门狗。
4. 准备多实例部署前，必须先实现第 5 节所有条件性接口及竞争测试。
