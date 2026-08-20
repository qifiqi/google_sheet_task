# `t_param_*` SDK 查询条件与问题审计

> 日期：2026-08-20
>
> 范围：仅审计当前项目实际使用的、与本地 `t_param_*` ORM 模型对应的 SDK 资源；不包含 `sys_*`，也不包含 `stock_data` 等非 Param 资源。
>
> 目的：为后续移除业务层本地 ORM 查询提供精确的查询条件、接口问题和实施优先级。本文不修改业务代码，也不要求新增测试脚本。

## 1. 审计口径

现有标准 CRUD 只有：

- `GetInfoById`
- `GetDataByPageList(page_index, page_size, order_field, order_type)`
- `ModifyOrAdd`
- `Delete`

它只能按主键读取，分页接口没有业务筛选或字段投影。以下结论中的“需要 Query”均指新增**带条件的只读查询接口**，而非把过滤搬到 Flask 全量拉取后处理。

“P0”表示若目标是移除对应业务路径中的所有 ORM 直连，则必须具备；“P1/P2”表示当前小数据量或单实例可暂缓，但应在对应场景启用前补齐。

## 2. 总览

| 资源 / 本地表 | 当前读取用途 | 结论 |
| --- | --- | --- |
| `ParamTasks` / `t_param_tasks` | 任务列表、仪表盘、看门狗、运行冲突检查、汇总重建 | **P0：通用 Query + 统计** |
| `ParamTaskLogs` / `t_param_task_logs` | 任务日志、看门狗最新日志、保留期清理、任务删除 | **P0：按任务/时间 Query** |
| `ParamTaskResults` / `t_param_task_results` | 结果页、运行态、导出、结果清理、模型汇总 | **P0：按任务/结果 ID Query + 投影** |
| `ParamTaskResultsReturn` / `t_param_task_results_return` | 回测收益序列、运行态图表、任务删除 | **P0：按任务/ID Query** |
| `ParamTaskResultSummaryIndex` / `t_param_task_result_summary_index` | 汇总页面、重建、结果/任务清理 | **P0：索引 Query；此前“不需要”的前提不成立** |
| `ParamBacktestProductResultCache` / `t_param_backtest_product_result_cache` | 多品回测缓存命中、重复键后重读 | **P0：业务键 Query** |
| `ParamBacktestSheetRunLocks` / `t_param_backtest_sheet_run_locks` | Sheet 互斥、任务清理 | **P0：按 `task_id` 查询；租约为 P1** |
| `ParamXplAnalysisJobs` / `xpl_analysis_jobs` | 删除任务/结果时清理关联 XPL 作业 | **P0：关联条件 Query；当前仍是裸表直连** |
| `ParamStockMetadata` / `t_param_stock_metadata` | 股票搜索元数据缓存读取、更新 | **P0：业务键 Query** |
| `ParamGoogleSheetTokens` / `t_param_google_sheet_tokens` | Token 选择、容量展示 | **P0：可用 Token Query；原子预占为 P1** |
| `ParamGoogleSheet` / `t_param_google_sheet` | 注册表展示、同类 Sheet 判重、删除前占用检查 | P1：规模化时下推筛选；唯一约束必须保留 |
| `ParamScheduledTasks` / `t_param_scheduled_tasks` | 加载启用任务、默认任务判重、运行状态 | P1：启用态/业务键查询；多实例 Claim 为 P1 |
| `ParamSystemConfigs` / `t_param_system_configs` | 配置缓存、配置页面 | P2：按 key/keys 查询即可 |
| `ParamTaskTemplates` / `t_param_task_templates` | 模板分页展示、按 ID 回填 | 现阶段无必需新增查询 |

## 3. P0：应先补齐的查询条件

### 3.1 `ParamTasks/Query`

代码涉及 `app/services/task/query.py`、`dashboard_query.py`、`task_watchdog.py`、`model_summary_service.py`。任务页面不仅要列表，还要在**筛选后的结果集**上计算状态统计和平均耗时。

建议请求：

```json
{
  "page_index": 1,
  "page_size": 20,
  "ids": ["uuid"],
  "exclude_ids": ["uuid"],
  "task_types": ["google_sheet", "backtest_training"],
  "statuses": ["running", "error"],
  "created_by_user_id": 1,
  "keyword": "名称、描述或任务 ID",
  "created_from": "2026-08-15T00:00:00",
  "created_to": "2026-08-20T23:59:59",
  "current_step_gt": 0,
  "error_message_prefix": "[NETWORK_RETRYABLE]",
  "error_message_not_prefix": "[WATCHDOG_ABANDONED]",
  "fields": ["id", "status", "task_type", "created_at"],
  "sort": [{"field": "created_at", "direction": "desc"}],
  "include_statistics": true
}
```

问题与约束：

- `pending` 在现有代码中不是简单的状态筛选，而是 `status=pending AND current_step>0`；不能丢掉该条件。
- 看门狗只看近 5 天的 `running/error/cancelled` 任务，并要按错误消息前缀排除已放弃项。若服务端不支持前缀条件，至少必须支持 `created_from + statuses`，再由应用对这个小集合做前缀判断。
- `include_statistics` 应在同一筛选集返回 `total/completed/running/error/pending/today_new/avg_duration_minutes`，避免应用端重新扫全部任务。
- `fields` 供看门狗、汇总重建等轻量路径使用，避免传输 `config` 等大字段。

### 3.2 `ParamTaskLogs/Query`

代码涉及 `app/services/task/logs.py`、`task_watchdog.py`、`runtime_view.py`、`scheduler_service.py`、`scheduled_task_worker.py`、`task/data_cleanup.py`。

建议请求条件：`task_id`、`task_ids`、`ids`、`levels`、`timestamp_from`、`timestamp_to`（清理使用 `timestamp_before`）、`after_id`、`limit/page_index/page_size`、`sort`、`fields`。

关键问题：

- `sort=[timestamp desc, id desc] + limit=1` 必须能可靠取得看门狗的最新日志；时间相同不能只按 timestamp 排序。
- 任务详情读取“最新 N 条再反转为正序”，应支持 `limit`，而不是读取任务的所有日志。
- 保留期清理需要用 `timestamp_before + fields=[id]` 分批取 ID，再调用已有 `Delete`；不应先拉取全表。
- 远程索引至少应覆盖 `(task_id, timestamp, id)` 和 `timestamp`。

### 3.3 `ParamTaskResults/Query`

代码涉及 `task/results.py`、`task/runtime_view.py`、`backtest_training*.py`、`backtest_multi_product*.py`、`template_api.py`、`model_summary_service.py` 与清理任务。

建议请求条件：`task_id`、`task_ids`、`ids`、`step_index_from`、`step_index_to`、`success`、`has_return_series`、`timestamp_from`、`timestamp_to/timestamp_before`、分页、`sort`、`fields`、`include_counts`。

关键问题：

- `task_ids` 不是可有可无的优化：模型汇总和全局预览存在跨任务读取，不能循环全表或对每个任务发一次请求。
- 普通结果列表、导出和汇总所需字段不同。`fields` 必须支持只取 `id/task_id/step_index/success/timestamp/return_series_id`，需要详情时再取 `parameters/result/error_message`，避免大 JSON 全量传输。
- `include_counts` 返回 `total/success_total/failed_total`，对应当前结果分页页面的统计。
- 保留期清理以 `timestamp_before + fields=[id, return_series_id]` 分批读取，再调用已有 Delete；清理前不需要返回参数和结果 JSON。
- 推荐服务端索引：`(task_id, step_index)`、`(task_id, timestamp)`、`(success, timestamp)`；现有本地模型已有等价索引。

### 3.4 `ParamTaskResultsReturn/Query`

建议请求条件：`task_id`、`task_ids`、`ids`、`stock_date_from`、`stock_date_to`、分页、`sort`、`fields`。

关键问题：

- `return_series_id` 实际就是此资源的 `id`，单条详情可继续使用 `GetInfoById`；按任务画备用收益曲线和任务删除则必须使用 `task_id` 查询。
- `returns_json` 内的 dates 是 JSON 数组，不能把 `stock_date_from/to` 误认为能准确过滤 JSON 内的每个日期。日期条件只适用于表级 `stock_date`；若要裁剪 JSON 收益曲线，应由应用端裁剪，或将序列拆为可查询行后再要求服务端过滤。
- 运行态图表最多展示 120 点，建议支持 `sort=stock_date desc + limit=120`；拿到后由应用反转。

### 3.5 `ParamTaskResultSummaryIndex/Query`

此前审计认为该资源不必新增 Query，但这只适用于“不迁移现有汇总页面和清理逻辑”的情况。当前 `model_summary_service.py` 直接按 `task_id`、`task_result_id`、任务类型、市场、区间、最佳标志、股票关键字等筛选，并使用窗口函数选出每只股票/每个分组的最新最优行；`task/data_cleanup.py` 还必须先查出关联索引 ID 才能逐条 Delete。因此在“移除所有 ORM 直连”目标下它是 P0。

建议基础 Query 条件：`task_id`、`task_ids`、`task_result_id`、`task_result_ids`、`task_type/task_types`、`market_type`、`stock_code`、`keyword`（股票代码/名称/任务名）、`period_key`、`is_best`、`best_metric_value_gt`、`result_timestamp_from/to`、`ids`、分页、排序、`fields`。

仍需确认的接口问题：

1. 现有页面的“每只股票取最新最佳值”和“每任务/分组取最新值”是窗口函数语义，普通 Query 无法保证正确分页。服务端应提供 `latest_per=stock_code|task_and_period`，或独立投影接口；不能先分页后在应用端去重。
2. 汇总页需要稳定的白名单排序：`result_timestamp`、`best_metric_value`、`stock_code`、`id`，禁止直接拼接客户端字段。
3. 清理仅需 `fields=[id]`，重建展示才需要 `metrics_json/parameter_summary`。

### 3.6 `ParamBacktestProductResultCache/QueryByBusinessKey`

建议请求：`batch_id`、`cache_key`；响应支持 `fields`。

这是缓存命中和唯一键冲突后“重新读取先成功写入者”的必需能力。响应最少要能取 `id/result_json/returns_json/source_task_id/source_step_index`。远端必须保留 `UNIQUE(batch_id, cache_key)`，并把冲突稳定映射为 `409` 或 `DUPLICATE_KEY`。

### 3.7 `ParamBacktestSheetRunLocks/Query`

建议请求条件：`spreadsheet_id`、`task_id`、`task_ids`、`ids`、`created_before/updated_before`、`fields`。

`spreadsheet_id` 的互斥仍可用“新增 + `UNIQUE(spreadsheet_id)` + 冲突处理”实现，不必新增专用获取锁 Action；但当前任务清理代码按 `task_id` 找锁并删除，基础 CRUD 无法替代，故该 Query 为 P0。远端 Delete 还应校验锁归属，防止误删其他任务的锁。

多实例或进程可能失联时，再补 `AcquireLease/RenewLease/ReleaseByTask`；这属于 P1，不是当前单实例的前置条件。

### 3.8 `ParamXplAnalysisJobs/Query`

SDK 已有该 Param 资源，但项目未建立 Repository；`app/services/task/data_cleanup.py` 仍通过反射本地 `xpl_analysis_jobs` 表，按 `task_id`、`task_result_id`、`return_series_id` 删除关联作业。

建议先补：`Query(task_id, task_result_ids, return_series_ids, ids, fields=[id])`，然后应用循环调用已有 Delete。若关联作业量大，后续再增加 `DeleteByAssociation`，但这不是先决条件。

需要确认 SDK DTO 的字段类型：当前生成 DTO 将 `task_result_id`、`return_series_id`、`attempts` 写成字符串，而本地关联 ID/计数是整数；服务端协议应统一为数值或明确允许字符串数值，避免匹配失效。

### 3.9 `ParamStockMetadata/QueryByBusinessKey`

建议请求：`stock_code`、`market_type`，响应返回最新记录或空值。

本地逻辑以 `(stock_code, market_type)` 精确查找，随后更新同一记录；因此服务端需保留同名唯一约束。当前不需要按股票名称模糊查询或批量代码查询，除非后续把搜索结果缓存批量预热。

### 3.10 `ParamGoogleSheetTokens/Query`

建议请求条件：`task_types`、`is_active`、`available_only`、`token_ids`、`name_keyword`、分页、排序、`fields`。

`available_only` 必须明确定义为：`is_active=true AND (max_usage_count=0 OR current_in_use_count < max_usage_count)`。Token 选择还依赖排序：`current_in_use_count asc`、`task_usage_count asc`、`id asc`。

安全和并发问题：

- 列表和默认详情都不得返回 `token_context`；仅在经授权的单条读取显式 `include_context=true` 时返回。
- Query 只能筛出“当时可用”，不能原子占用。若部署多实例，必须增加 `Reserve/ReleaseByTask`（或带条件的原子计数更新）；单实例可先由进程内锁串行化。

## 4. P1/P2：当前可暂缓，但要记录接口边界

| 资源 | 建议条件 / 约束 | 当前为何可暂缓 |
| --- | --- | --- |
| `ParamGoogleSheet` | `Query(spreadsheet_id, registry_scope, table_type, is_active, is_in_use, current_task_id, keyword)`；服务端保留 `UNIQUE(spreadsheet_id, registry_scope)` | 当前注册表通过 `page_size=1000` 单页读取再筛选，仅能提供友好提示；唯一约束才是正确性保证。超过单页或需要服务端分页展示时升为 P0。 |
| `ParamScheduledTasks` | `Query(is_active, task_function, name, next_run_before, is_running)`；建议为默认清理任务建立 `UNIQUE(name, task_function)` 或提供精确业务键查询 | 当前单调度实例可读取全部后筛选。多调度器时必须补 `ClaimRun/CompleteRun`，不能依赖读取 `is_running` 后再写回。 |
| `ParamSystemConfigs` | `QueryByKey(key)` 与 `Query(keys)`，可选 `fields` | 配置量很小，现有实现可分页读取后缓存；但 `get_by_key()` 每次全量遍历，长期应补精确查询。 |
| `ParamTaskTemplates` | 若模板量增大再加 `Query(task_type, keyword, created_by_user_id, ids, is_active)` | 当前业务已能以标准分页列表和按 ID 读取满足页面用途，没有必须的 ORM 条件查询。 |

## 5. 共同协议问题与实施顺序

### 共同协议

1. Query 只允许固定字段和固定排序白名单；不能向 SQL 透传任意 `order_field`、表达式或 where 字符串。
2. 列表统一返回 `items/total`；统计统一置于 `statistics`，避免把 `total` 和不同计数混用。
3. 支持 `fields` 时，服务端仍须强制返回主键和后续分页所需游标字段；敏感字段不因 `fields` 而绕过脱敏。
4. 所有时间以 ISO-8601（带时区或明确 UTC）传输，时间范围明确包含边界规则。
5. 唯一键冲突必须返回可识别的 `409/DUPLICATE_KEY`；不得静默把“新增”变成覆盖另一条业务记录。
6. 远端需保留与上述过滤条件相匹配的组合索引；否则新增 Query 只会把全表扫描从 Flask 移到服务端。

### 推荐顺序

1. 先实现 `Tasks`、`TaskLogs`、`TaskResults`、`TaskResultsReturn` 的 Query：它们覆盖任务主页面、运行态、看门狗与清理主链路。
2. 再实现 `SummaryIndex`、`XplAnalysisJobs`、`BacktestSheetRunLocks` 的关联查询，才能完整移除任务删除/重建时的 ORM 直连。
3. 实现 `StockMetadata`、回测缓存、Token 查询和唯一冲突协议，完成搜索缓存、回测复用和资源选择。
4. 最后按数据规模决定 Sheet、定时任务、配置、模板的可选 Query；准备多实例前补原子 Reserve/Claim/Lease。

## 6. 验收清单

- `app/services`、`app/routes`、`app/utils` 中针对上述 `t_param_*` 的读取不再调用 `Model.query`、`db.session.query`、反射 `Table` 或本地 ORM 聚合。
- 不允许以 SDK 的无筛选分页接口拉取全表后模拟 P0 条件。
- 任务列表统计、看门狗最新日志、结果分页统计、任务删除关联清理、汇总页面“每组最新最优”均在远端语义正确。
- Token 默认响应不泄漏 `token_context`；重复 Sheet、重复缓存和重复锁均返回可识别的唯一冲突。
- 本文未要求新增或修改测试脚本；接口落地后再按实际变更范围补充定向验证。
