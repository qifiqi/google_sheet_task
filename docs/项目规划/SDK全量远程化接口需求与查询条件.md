# SDK 全量远程化接口需求与查询条件

> 文档版本：v1.1  
> 日期：2026-08-19  
> 目标：使 Flask 应用的业务数据读写统一经由 `app/repositories` → `stock_sdk` → 远程服务完成，并在保证任务一致性与可恢复性的前提下移除业务代码对本地数据库的直连。

## 1. 结论

现有 SDK 已覆盖 13 张核心业务表的基础 CRUD：按 ID 查询、无业务筛选的分页、单条新增/修改、单条删除。并非所有业务规则都要变成新 HTTP 接口：字段校验、DTO 转换、权限前置判断、小规模控制数据的列表筛选、普通单条 CRUD 和“唯一冲突后的错误提示”均可保留在 Flask Service/Repository 层。

不能以“客户端取全量记录再过滤/判断后修改”替代缺失接口。这会造成全表扫描、分页总数失真，以及 Token、Google Sheet、运行锁和任务状态的并发竞争。

本次复核后，接口按两层划分：

| 类别 | 数量 | 目的 |
| --- | ---: | --- |
| 最小新增查询接口 | 8 | 仅保留无法通过基础 CRUD 高效、正确实现的业务键查询、结果读取与汇总 |
| 最小新增命令接口 | 3 | 仅保留必须由远程数据库原子完成的状态转换、Token 预留和批量执行落库 |
| 未被当前 SDK 覆盖的资源接口 | 3 组 | 认证、RBAC 与导航菜单，当前 SDK 模型不能直接替代 |
| 规模化/多实例增强接口 | 其余 Q/C 项 | 当数据量、可用性或多应用实例要求提升时再增加 |

本文第 4、5 节保留完整的规模化接口目录，便于后续演进；第 3.4 节是当前应优先落地的最小集合。新增后应重新生成 `stock_sdk`，而不是在 Flask 中手写 HTTP 请求。

## 2. 现状与边界

### 2.1 当前 SDK 可映射的数据表

| 本地模型 | SDK Controller | 已有基础能力 | 全量迁移缺口 |
| --- | --- | --- | --- |
| `Task` | `ParamTasks` | CRUD、分页 | 任务筛选、状态机、仪表盘、看门狗、批量读取 |
| `TaskLog` | `ParamTaskLogs` | CRUD、分页 | 按任务/级别/时间检索、批量写入、保留期清理 |
| `TaskResult` | `ParamTaskResults` | CRUD、分页 | 按任务/结果 ID 集合读取、分页统计、批量写入/删除、导出 |
| `TaskResultReturn` | `ParamTaskResultsReturn` | CRUD、分页 | 按任务与日期区间读取、批量写入/删除 |
| `BacktestProductResultCache` | `ParamBacktestProductResultCache` | CRUD、分页 | 业务键查询与原子 Upsert |
| `BacktestSheetRunLock` | `ParamBacktestSheetRunLocks` | CRUD、分页 | 按 Sheet 加锁/续租/释放 |
| `TaskResultSummaryIndex` | `ParamTaskResultSummaryIndex` | CRUD、分页 | 汇总查询、批量重建、最优记录去重 |
| `StockMetadata` | `ParamStockMetadata` | CRUD、分页 | 按代码+市场查询/Upsert、搜索 |
| `TaskTemplate` | `ParamTaskTemplates` | CRUD、分页 | 名称筛选（建议） |
| `SystemConfig` | `ParamSystemConfigs` | CRUD、分页 | 按 key 批量读取/写入 |
| `GoogleSheetToken` | `ParamGoogleSheetTokens` | CRUD、分页 | 业务筛选、原子占用/释放、统计 |
| `GoogleSheet` | `ParamGoogleSheet` | CRUD、分页 | 新增/更新可复用唯一约束；占用改用既有运行锁的通用 CRUD，不必新增 Sheet 占用 Action |
| `ScheduledTask` | `ParamScheduledTasks` | CRUD、分页 | 启停、实例抢占、统计、运行状态更新 |

### 2.2 当前 SDK 不能直接替代的本地资源

| 本地资源 | 原因 | 需要的远程资源 |
| --- | --- | --- |
| `User`、`Role`、`Permission`、关联表 | `sys_user`、`sys_role` 与本项目字段、密码散列、权限关系和鉴权语义不一致 | `Identity` / `AccessControl` 专用接口组 |
| `NavigationMenuItem` | SDK 无对应表/接口 | `NavigationMenu` 接口组 |
| 启动期 schema 修补与迁移 | 属于数据库运维，不应经由业务 SDK 模拟 | 迁移职责保留在远程数据服务部署侧 |
| 本地线程注册表 | `running_tasks`、停止事件等是进程内运行态，不是持久化数据 | 保留在 Flask；远程仅持久化任务状态和资源租约 |

## 3. 接口统一约定

### 3.1 协议与返回

- 延续 SDK 现有 `POST /api/{Controller}/{Action}` 风格，所有新增接口使用 JSON 请求体。
- 成功与失败均使用 `ResponseDto`：`ret_code`、`ret_msg`、`ret_obj`；`ret_code != 200` 时 Repository 必须映射为领域异常。
- 时间字段统一 ISO 8601（带时区）；列表区间采用左闭右开：`[from, to)`。
- 所有会写入或占用资源的命令均接收 `request_id`（UUID）；同一 `request_id` 重试必须幂等。
- 所有受数据权限保护的查询与命令均由远程服务根据调用身份鉴权；客户端不传可伪造的 `user_id` 作为权限依据。

### 3.2 通用分页与排序 DTO

现有 `RequsetPageDto` 不应继续用于业务查询。新增 `QueryPageDto`：

```json
{
  "page_index": 1,
  "page_size": 50,
  "sort": [{"field": "created_at", "direction": "desc"}],
  "include_total": true
}
```

- `page_size` 服务端限制为 1–200；导出、流式读取使用专用接口，不允许将 `page_size` 放大到全量。
- `sort.field` 只能是接口白名单字段，禁止将客户端字符串拼接为 SQL。
- 每个列表响应固定返回：`items`、`page_index`、`page_size`、`total`、`pages`、`has_next`。
- `fields` 可作为可选投影字段，仅允许白名单字段；用于结果列表避免返回巨大的 `result`/`parameters` JSON。

### 3.3 事务边界

下列动作必须在远程服务的单个数据库事务内完成：条件状态变更、占用/释放、锁租约、任务及结果的级联删除、批量结果写入、汇总索引 Upsert。HTTP 客户端只能得到最终结果，不能自行编排“读—判断—写”。

### 3.4 v1.1 最小新增接口与业务侧实现边界

| 类型 | 当前最小新增项 | 不新增接口、由业务侧实现的部分 |
| --- | --- | --- |
| 任务 | `ParamTasks/Query`、`CompareAndSetStatus` | 普通详情 `GetInfoById`、单条配置修改 `ModifyOrAdd`、C31 循环创建及失败补偿 |
| 日志与结果 | `ParamTaskLogs/Query`、`ParamTaskResults/Query`、`ParamTaskResultsReturn/Query`、`ParamTaskExecution/AppendBatch` | JSON 反序列化、导出 Excel、分页 DTO 到页面格式转换 |
| 股票与缓存 | `ParamStockMetadata/Query`、`ParamBacktestProductResultCache/GetByBusinessKey` | 缓存写入使用已有 `ModifyOrAdd`；发生唯一冲突后重新读取业务键 |
| Token | `ParamGoogleSheetTokens/Query`、`Reserve` | Token 文件 UTF-8 落地、JSON 格式校验、展示脱敏、释放时按已持久化预留记录处理 |
| Sheet 注册与锁 | **无新增 Action**；复用 `ParamGoogleSheet` 与 `ParamBacktestSheetRunLocks` 的 CRUD | 输入校验、唯一冲突提示、锁 ID 持久化、同进程等待队列与启动期清理 |
| 汇总 | `ParamTaskResultSummaryIndex/QuerySummary` | CSV/Excel 渲染；索引重建可先在 Flask 以 SDK 分页读取和 CRUD 写回实现 |
| 认证与菜单 | `Identity`、`AccessControl`、`NavigationMenu` 三组资源 | 前端菜单渲染与本地会话包装 |

上述“业务侧实现”有两个前提：

1. 业务侧不得连接数据库，只能通过 Repository 调用 SDK 的现有 CRUD。
2. 远程数据服务必须保留并暴露唯一约束冲突；对不可并行的资源，业务侧以“创建唯一锁记录”代替读取后更新状态。

### 3.5 Google Sheet 新增校验与锁的具体方案

#### 注册表新增/更新：不需要新接口

`t_param_google_sheet` 已有唯一约束 `spreadsheet_id + registry_scope`。新增和修改可按下述流程复用已有 `ParamGoogleSheet/ModifyOrAdd`：

1. Service 在业务侧校验 `spreadsheet_id` 非空、`table_type` 合法，并计算 `registry_scope`。
2. 可选地在当前已加载页面内检查重复，仅用于尽早给出友好提示；**不能**将这一步作为一致性保证。
3. 调用 `ModifyOrAdd` 保存；远程数据库的复合唯一约束才是最终裁决。
4. 将唯一约束冲突转换为“该 spreadsheet_id 已存在于同类表类型中”的领域错误；不重试为其他值。

因此，现有 `GoogleSheetRegistryService.create_sheet()` / `update_sheet()` 中为去重而读取 `page_size=1000` 后在本地筛选的写法，应在后续改造时删除。它既不能覆盖第 1001 条记录，也无法避免并发创建竞态。

删除前可用 `GetInfoById` 做友好校验；远程 `Delete` 仍必须在存在运行锁/占用记录时拒绝删除，避免“校验后被占用”的竞态。这是基础 CRUD 的服务端约束，不是新增业务 Action。

#### 运行锁：可复用既有通用 CRUD，不需要 `AcquireLease` 等新 Action

当前 `t_param_backtest_sheet_run_locks` 已有唯一约束 `spreadsheet_id`，本地实现也是“尝试插入，捕获 `IntegrityError`”而不是先加行锁。因此迁移后可以使用已有 SDK：

1. 以 `id=null` 调用 `ParamBacktestSheetRunLocks/ModifyOrAdd` 创建 `{spreadsheet_id, task_id, task_type}`。
2. 成功即持锁；唯一冲突即表示被其他任务持锁。应用将返回的 `lock_id` 写入任务配置或运行态登记。
3. 正常结束、取消和异常处理时，按 `lock_id` 先 `GetInfoById` 核验 `task_id`，再调用 `Delete`；重复释放应视为成功。
4. 启动恢复时，按任务配置保存的锁 ID 清理；未登记的遗留锁可作为低频运维扫描处理。

这个方案满足当前“单 Flask 进程 + 后台线程 + 启动期恢复”架构，且不新增接口。前提是远程 `ModifyOrAdd` 的新增语义必须让数据库唯一冲突以可识别业务错误（建议 HTTP 409 或 `ret_code=409`）返回，不能把重复请求静默覆盖为其他任务的锁。

当部署多 Flask 实例、需要锁自动过期，或不能可靠持久化 `lock_id` 时，才升级为第 C16–C18 的租约接口。当前 SDK 锁模型没有 `lease_expires_at`，因此“租约”不是当前最小方案的一部分。

## 4. 必须新增的查询接口与查询条件

### Q01. 任务列表与统计

`POST /api/ParamTasks/Query`

```json
{
  "page_index": 1,
  "page_size": 20,
  "task_types": ["google_sheet", "backtest_training"],
  "statuses": ["running", "error"],
  "keyword": "AAPL",
  "created_by_user_id": 12,
  "created_from": "2026-08-01T00:00:00+08:00",
  "created_to": "2026-08-20T00:00:00+08:00",
  "current_step_gt": 0,
  "include_statistics": true,
  "sort": [{"field": "created_at", "direction": "desc"}]
}
```

查询条件：`task_types`、`statuses`、`keyword`（匹配 `id/name/description`）、创建人、创建/开始/结束时间区间、`current_step`、`has_error`。`include_statistics=true` 时返回筛选集的状态数量、今日新增、成功率、失败率和平均耗时；不得另行全表统计。

### Q02. 任务仪表盘

`POST /api/ParamTasks/GetDashboardOverview`

查询条件：`task_types`、`created_from`、`created_to`、`trend_days`（1–90）、`recent_limit`（1–50）、`active_limit`（1–50）。返回状态分布、任务类型分布、按日创建/完成趋势、最近任务、运行中任务。任务类型权限由服务端从身份推导。

### Q03. 任务批量精确读取

`POST /api/ParamTasks/GetByIds`

请求：`ids`（1–100 个 UUID）、`fields`。用于批量导出前的授权校验和名称读取；必须保留输入 ID 与结果的对应关系，并返回不存在的 ID 列表。

### Q04. 等待任务查询

`POST /api/ParamTasks/FindPendingBySheets`

查询条件：`spreadsheet_ids`、`task_types`、`exclude_task_id`、`limit`（默认 1）。固定按 `created_at ASC, id ASC` 返回，以保持当前同 Sheet 回测任务的 FIFO 行为。

### Q05. 看门狗候选任务查询

`POST /api/ParamTasks/FindWatchdogCandidates`

查询条件：`created_from`（当前为最近 5 天）、`statuses`、`stale_before`、`retryable_error_prefix`（当前为 `[NETWORK_RETRYABLE]`）、`limit`、`cursor`。响应应附带最近日志时间、是否存在有效锁、重试次数和可重启原因，避免 Flask 逐任务再查日志。

### Q06. 任务日志查询

`POST /api/ParamTaskLogs/Query`

查询条件：`task_id`（必填）、`levels`、`timestamp_from`、`timestamp_to`、`keyword`、`after_id` / `before_id`、`limit`（1–500）、`sort`。轮询场景建议使用 `after_id` 或 `timestamp_gt`，不要每次取最近 500 条再在客户端去重。

### Q07. 任务结果查询

`POST /api/ParamTaskResults/Query`

查询条件：`task_id`（必填）、`ids`、`step_index_from`、`step_index_to`、`success`、`timestamp_from`、`timestamp_to`、`include_counts`、`fields`、分页与排序。默认排序为 `step_index ASC, timestamp ASC, id ASC`。`include_counts=true` 返回 `total/success_total/failed_total`，以替代本地二次计数。

### Q08. 全局预览结果读取

`POST /api/ParamTaskResults/QueryPreviewData`

查询条件：`task_id`（必填）、`result_ids`（可选，最多 1,000）、`stock_codes`（可选）、`success`、`fields`。返回完整 `parameters/result` 所需数据；普通列表接口不得默认返回大 JSON。此接口是 C3 汇总、全局预览和按股票导出的数据源。

### Q09. 收益序列查询

`POST /api/ParamTaskResultsReturn/Query`

查询条件：`task_id`（必填）、`stock_date_from`、`stock_date_to`、`ids`、`fields`、分页/排序。默认 `stock_date ASC, id ASC`；`returns_json` 仅在详情或明确字段投影时返回。

### Q10. 股票元数据读取与搜索（最小实现只需 `Query`）

| 接口 | 查询条件 |
| --- | --- |
| `POST /api/ParamStockMetadata/GetByCodeAndMarket` | `stock_code`、`market_type`，二者必填；返回单条或明确空结果。可由支持精确筛选的 `Query` 替代 |
| `POST /api/ParamStockMetadata/Search` | `keyword`、`market_types`、`exchange_market`、`security_type_name`、`sources`、`limit`（1–50）。属于规模化增强 |

查询结果按精确代码优先、其次代码前缀、最后名称匹配排序。`stock_code + market_type` 是业务唯一键，不能依赖客户端全量分页查找。

### Q11. Token 列表与可用性查询（最小实现只需 `Query`）

`POST /api/ParamGoogleSheetTokens/Query`

查询条件：`task_types`、`is_active`、`available_only`、`token_ids`、`name_keyword`、`last_used_from/to`、`include_usage`、分页/排序。敏感的 `token_context` 默认永不返回；只有独立受限的详情接口可在授权后返回。

### Q12. Token 使用统计

`POST /api/ParamGoogleSheetTokens/GetUsageSummary`

查询条件：`task_types`、`is_active`。返回当前总占用、累计使用、启用数量、可用数量、全局上限及各 Token 的占用摘要；计算必须在远程服务执行。

### Q13. Google Sheet 注册表查询（规模化增强）

`POST /api/ParamGoogleSheet/Query`

查询条件：`ids`、`spreadsheet_ids`、`table_types`、`registry_scopes`、`is_active`、`is_in_use`、`current_task_id`、`name_keyword`、分页/排序。创建和更新的最终唯一性判断不依赖该查询接口，而由远程数据库的 `spreadsheet_id + registry_scope` 唯一约束完成。

### Q14. 活跃运行锁查询（规模化增强）

`POST /api/ParamBacktestSheetRunLocks/QueryActive`

查询条件：`spreadsheet_ids`、`task_id`、`task_types`、`expired_before`、分页/排序。用于启动恢复、看门狗排障和回测排队；返回租约到期信息。

### Q15. 多品回测缓存查询

`POST /api/ParamBacktestProductResultCache/GetByBusinessKey`

查询条件：`batch_id`、`cache_key`（均必填）。可选 `source_task_id`、`source_step_index` 用于审计。该查询是缓存命中判断，必须走唯一索引。

### Q16. 单模型汇总查询

`POST /api/ParamTaskResultSummaryIndex/QuerySummary`

查询条件：`task_type`、`task_id`、`task_result_id`、`stock_code`（代码或名称关键字）、`market_type`、`period_key`、`result_date_from/to`、`best_only`、`excess_return_min`、`summary_type`（`task`/`stock`）、分页/排序。响应同时返回列定义、汇总指标、分页数据。远程服务应处理权限允许的 `task_type`，而非接受客户端伪造的许可范围。

### Q17. 定时任务列表与统计（规模化增强）

`POST /api/ParamScheduledTasks/Query`

查询条件：`task_types`、`is_active`、`is_running`、`name_keyword`、`next_run_from/to`、`last_run_from/to`、`running_instance_id`、分页/排序；`include_statistics` 返回总数、启用数、运行数和下次执行时间。

### Q18. 系统配置批量读取（规模化增强）

`POST /api/ParamSystemConfigs/GetByKeys`

查询条件：`keys`（1–100）、`include_description`。应用启动及 `config_manager` 可一次获取所需配置，避免分页扫描和逐 key 请求。

### Q19. 认证、权限与菜单读取

当前 SDK 不适配，需新增三组接口：

- `Identity/GetCurrentUser`、`Identity/QueryUsers`：用户状态、用户名关键字、角色、创建时间。
- `AccessControl/QueryRoles`、`AccessControl/QueryPermissions`、`AccessControl/GetUserPermissions`：用户 ID、角色 ID、权限编码前缀。
- `NavigationMenu/QueryTree`：`parent_key`、`is_visible`、调用者权限；固定按 `sort_order ASC, id ASC`。

## 5. 必须新增的命令与事务接口

### 5.1 任务生命周期与持久化

| 编号 | 接口 | 关键请求字段 | 事务语义 |
| --- | --- | --- | --- |
| C01 | `ParamTasks/CreateBatch` | `tasks[]`、`request_id` | C31 子任务创建全成或全不成，返回每个 ID |
| C02 | `ParamTasks/CompareAndSetStatus` | `task_id`、`expected_statuses`、`target_status`、`patch`、`request_id` | 条件更新；不匹配返回 `conflict`，用于 pending→running、running→结束态 |
| C03 | `ParamTasks/UpdateProgress` | `task_id`、`expected_status=running`、`current_step`、`total_steps`、`request_id` | 不允许结束态回写进度 |
| C04 | `ParamTasks/Finalize` | `task_id`、`expected_status`、`final_status`、`end_time`、`error_message`、`release_resources`、`request_id` | 更新结束状态并释放该任务所有资源；必须幂等 |
| C05 | `ParamTasks/Cancel` | `task_id`、`expected_statuses`、`reason`、`request_id` | 原子取消并释放资源；内存停止信号仍由 Flask 发出 |
| C06 | `ParamTasks/DeleteCascade` | `task_id`、`include_logs`、`request_id` | 规模化增强：删除 Task、结果、收益序列、索引、锁与关联资源；小规模下可由 Service 按既有 CRUD 编排 |
| C07 | `ParamTasks/ClaimNextPendingForSheets` | `spreadsheet_ids`、`task_types`、`worker_id`、`lease_seconds`、`request_id` | FIFO 取一条待执行任务并标记运行；避免多进程同时启动 |
| C08 | `ParamTaskExecution/AppendBatch` | `task_id`、`logs[]`、`results[]`、`return_series[]`、`progress`、`request_id` | 批量写入执行产物与进度，全部提交或回滚 |
| C09 | `ParamTaskResults/PurgeByRetention` | `before`、`batch_size`、`request_id` | 规模化增强：服务端分批清理，并返回删除数量与游标 |
| C10 | `ParamTaskLogs/PurgeByRetention` | `before`、`batch_size`、`request_id` | 规模化增强：同上，不返回被删除正文 |

### 5.2 Token、Google Sheet 与回测锁

| 编号 | 接口 | 关键请求字段 | 事务语义 |
| --- | --- | --- | --- |
| C11 | `ParamGoogleSheetTokens/Reserve` | `task_id`、`task_type`、`token_id`（可选）、`request_id` | 最小新增：校验启用、类型、单 Token 上限和全局上限后占用；未指定 ID 时由服务端选择并返回 Token |
| C12 | `ParamGoogleSheetTokens/ReleaseByTask` | `task_id`、`request_id` | Token 预留如果有独立记录则需要；否则可通过任务已保存的 Token ID 使用已有 CRUD 条件释放 |
| C13 | `ParamGoogleSheetTokens/ReconcileUsage` | `active_task_ids` 或服务端任务状态规则、`request_id` | 规模化增强：启动恢复时修正占用计数 |
| C14 | `ParamGoogleSheet/AcquireForTask` | `sheet_id`、`task_id`、`request_id` | **不作为最小新增项**：当前回测互斥复用 `BacktestSheetRunLocks` 的唯一键 CRUD；若 C3/C4/C5 也要求跨实例互斥，再启用 |
| C15 | `ParamGoogleSheet/ReleaseByTask` | `task_id`、`request_id` | 同 C14；当前不新增 |
| C16 | `ParamBacktestSheetRunLocks/AcquireLease` | `spreadsheet_id`、`task_id`、`task_type`、`lease_seconds`、`request_id` | 规模化增强：当前可由锁表唯一键 + `ModifyOrAdd` 实现互斥 |
| C17 | `ParamBacktestSheetRunLocks/RenewLease` | `spreadsheet_id`、`task_id`、`lease_seconds`、`request_id` | 规模化增强：多实例/锁自动过期时启用 |
| C18 | `ParamBacktestSheetRunLocks/ReleaseByTask` | `task_id`、`request_id` | 规模化增强：当前按持久化 `lock_id` 循环 `Delete` |

### 5.3 缓存、汇总索引与计划任务

| 编号 | 接口 | 关键请求字段 | 事务语义 |
| --- | --- | --- | --- |
| C19 | `ParamBacktestProductResultCache/UpsertByBusinessKey` | `batch_id`、`cache_key`、结果数据、`request_id` | 规模化增强：最小实现可由 `ModifyOrAdd` 写入、唯一冲突后重新读取 |
| C20 | `ParamTaskResultSummaryIndex/Rebuild` | `task_type`、`task_id`、`reset`、`batch_size`、`request_id` | 规模化增强：远程异步作业；最小实现可在 Flask 分页读取、通过 SDK CRUD 回写 |
| C21 | `ParamTaskResultSummaryIndex/GetRebuildStatus` | `job_id` | 仅在启用 C20 的远程作业后需要 |
| C22 | `ParamTaskResultSummaryIndex/RefreshForTask` | `task_id`、`request_id` | 规模化增强：最小实现由 Flask 在任务结束时调用索引 CRUD |
| C23 | `ParamScheduledTasks/SetEnabled` | `task_id`、`is_active`、`expected_updated_at`、`request_id` | 最小实现可读取详情后 `ModifyOrAdd`；多管理端并发时升级为乐观锁 |
| C24 | `ParamScheduledTasks/ClaimRun` | `task_id`、`instance_id`、`lease_seconds`、`request_id` | 规模化增强：多调度实例时必需 |
| C25 | `ParamScheduledTasks/CompleteRun` | `task_id`、`instance_id`、`outcome`、`next_run_time`、`request_id` | 规模化增强：多调度实例时必需 |
| C26 | `ParamScheduledTasks/RecoverExpiredRuns` | `expired_before`、`request_id` | 规模化增强：多实例恢复时必需 |

### 5.4 业务键写入与未覆盖资源

| 编号 | 接口 | 关键请求字段 | 说明 |
| --- | --- | --- | --- |
| C27 | `ParamStockMetadata/UpsertByCodeAndMarket` | `stock_code`、`market_type`、元数据、`request_id` | 规模化增强：最小实现以 `ModifyOrAdd` + 唯一冲突重读处理 |
| C28 | `ParamSystemConfigs/UpsertBatch` | `items[]`、`request_id` | 规模化增强：少量配置可循环已有 `ModifyOrAdd` |
| C29 | `Identity/*` | 登录、刷新、密码变更、用户/角色绑定 | 需完整取代本地鉴权和用户管理；密码仅远程服务处理 |
| C30 | `AccessControl/*`、`NavigationMenu/*` | 角色权限关系、菜单树维护 | 覆盖权限校验与导航菜单 CRUD/排序 |

## 6. 推荐实现顺序

| 阶段 | 前置接口 | 迁移目标 | 验收标准 |
| --- | --- | --- | --- |
| P0 | Q10–Q13、Q17–Q18、C19、C23 | 完成配置、模板、元数据、Sheet 基础 CRUD 和计划任务普通读取 | Repository 不返回 ORM/SDK 响应对象；定向单测通过 |
| P1 | Q01、Q03、Q06–Q09、Q15、C08、C27 | 任务、日志、结果、收益序列和缓存读写走 Repository | C3/C4/C5/回测任务能创建、执行、查看、导出 |
| P2 | C02–C07、C11–C18、C24–C26、Q04–Q05、Q14 | 迁移状态机、占用锁、看门狗、调度与启动恢复 | 并发占用、取消、断点重启、网络恢复测试通过 |
| P3 | Q02、Q16、C20–C22 | 迁移仪表盘、单模型汇总与重建 | 查询/导出性能不依赖客户端全量扫描 |
| P4 | Q19、C29–C30 | 迁移认证、RBAC、菜单 | 远程授权结果与现有权限矩阵一致 |

## 7. 服务端实现要求

1. 为所有业务键建立数据库唯一索引：`stock_code + market_type`、`batch_id + cache_key`、`task_result_id + model_key`、`spreadsheet_id` 的运行锁等。
2. 对 C02、C11、C14、C16、C24 使用条件更新、唯一约束或 `SELECT ... FOR UPDATE` 等服务端并发控制；冲突返回可识别的业务码，例如 `409` / `RESOURCE_BUSY`。
3. Token 占用应有“任务—Token 预留”持久化记录或等价审计字段，不能只维护计数器，否则无法可靠执行 `ReleaseByTask` 与启动恢复。
4. 锁必须有租约过期时间；仅靠 `is_running` 或记录存在无法处理进程崩溃。
5. `QuerySummary`、仪表盘和保留期清理必须在远程数据服务执行筛选/聚合，Flask 只负责展示与业务编排。
6. `token_context`、密码散列、认证 Token 不得出现在普通列表、日志、异常 `ret_msg` 或导出接口中。
7. 每个新增 Action 应进入 Swagger/OpenAPI，并以其生成新的 `stock_sdk`。Repository 以 fake SDK 覆盖成功、空结果、业务冲突、超时和幂等重试。

## 8. 本次盘点的依据

- `stock_sdk/api/param_*.py`：现有核心 Controller 均为 `GetDataByPageList`、`GetInfoById`、`ModifyOrAdd`、`Delete` 的基础形态。
- `stock_sdk/models/*`：当前分页 DTO 缺少任何业务筛选字段。
- `app/services/task/*`：任务查询、结果、运行时状态、资源占用、清理和重启均存在多表或条件写操作。
- `app/services/model_summary_service.py`：单模型汇总依赖筛选、排序、聚合、批量 Upsert、去重与异步重建。
- `app/services/google_sheet_token_service.py`、`app/services/google_sheet_registry_service.py`：依赖 Token/Sheet 的容量和占用一致性。
- `app/services/scheduler_service.py`、`app/services/task_watchdog.py`、`app/startup.py`：依赖实例抢占、失效恢复和时间窗口查询。

## 9. 不应采用的替代方案

- 不要将通用分页 `GetDataByPageList` 的 `page_size` 调大后在 Flask 侧过滤。
- 不要用“读取 Token/Sheet → 判断 → `ModifyOrAdd`”实现占用；并发下会超额分配。
- 不要把单条 `Delete` 循环用于任务级联删除或保留期清理。
- 不要将任务状态、日志、结果拆为多个无事务 HTTP 调用；一次失败会留下不可恢复的中间状态。
- 不要以 SDK 中名称相近的 `sys_user`、`sys_role` 直接替换现有 User/RBAC，除非先完成字段、密码策略、关系和权限语义对齐。
