# 02 — 模型索引审计（MySQL 口径）

> 判定方法：`models.py` + 全部迁移取索引并集（含 `index=True` 隐式索引），对每个索引在 repositories/services 全量 grep 其**可服务的真实查询**（WHERE 列序 + ORDER BY）。判定只认证据，"未来可能用"不作为保留理由（用户明确要求移除此类索引）。

## 1. 前置事实

- 生产引擎 **MySQL/InnoDB**；复合索引遵循最左前缀；布尔单列索引基数≈2，优化器基本不选；
- **20260811 已清理过一轮**（`20260811_remove_unused_indexes.py`，删 32 个），方向正确，但存在"误删在用 + 漏删无效"双向偏差（§4/§5）；
- 模型与迁移当前一致（20260522 建的 6 个单列 `ix_*` 已由 20260811 对齐）；启动期 `app/startup.py` 存在 `_ensure_model_index()` 私自补索引逻辑（`startup.py:162`），是唯一残留的模型外索引来源；
- **startup.py 的 `_ensure_model_index` 补建点共 3 处**（校准 2026-09-05 实测）——:162（task_results.return_series_id，随本批移除）、:357（navigation idx_parent_sort）、:358（navigation ix_is_visible），后两处随对应索引移除同步删除；:150（ix_tasks_created_by_user_id）对应保留索引，不动；
- 表体量分布：tasks/task_results/task_logs/summary_index 为大表（持续增长），其余（RBAC、navigation、google_sheet、scheduled_tasks、token 池）均为百行级小表——小表索引只谈"语义正确"，不谈性能收益。

## 2. 现存索引全景与逐条判定

### 2.1 大表（保留为主）

| 表 | 索引 | 服务查询（证据） | 判定 |
|---|---|---|---|
| tasks | `idx_status_created(status,created_at)` | watchdog 待启动扫描 `runtime.py:282`（status= + ORDER created_at ✓ 完美命中）；`token_service.py:26` status='running' | **保留**（核心） |
| tasks | `idx_type_status(task_type,status)` | 任务列表组合过滤 `task_repository.py:44-48` | **保留** |
| tasks | `ix_tasks_created_at` | 列表/最近任务 `ORDER BY created_at DESC`（无 status 过滤路径） | **保留** |
| tasks | `ix_tasks_created_by_user_id` | 删用户置空 `clear_created_by`（低频但命中） | **保留** |
| task_logs | `idx_task_logs_task_timestamp(task_id,timestamp)` | 详情/最新日志 `task_log_repository.py:15-26` | **保留** |
| task_logs | `ix_task_logs_timestamp` | 清理 `delete_older_than` `task_log_repository.py:84` | **保留** |
| task_results | `idx_task_step(task_id,step_index)` | 详情分页/成功计数（task_id 前缀） | **保留** |
| task_results | `idx_task_results_task_timestamp(task_id,timestamp)` | `latest_time_by_task` ORDER timestamp DESC | **保留** |
| task_results | `ix_task_results_timestamp` | 清理 `delete_older_than` | **保留** |
| task_results | `idx_success_timestamp(success,timestamp)` | **全库无 `success+timestamp` 组合查询**（success 过滤均伴随 task_id，走 `idx_task_step` 前缀；`grep TaskResult.success` 证据见审计记录） | ❌ **移除** |
| task_results | `ix_task_results_return_series_id` | **零查询引用**：`return_series_id` 仅作为值读出（`backtest_training.py:142`），随后按 **TaskResultReturn 主键** 取数；且 `startup.py:162` 启动期自动重建 | ❌ **移除**（须同步删 startup 重建行） |
| task_results_return | `ix_task_results_return_task_id` | `get_returns_by_task` / `delete_returns_by_task` / cleanup | **保留** |
| task_results_return | `ix_..._stock_code` / `ix_..._stock_name` | 无任何按这两列的查询（该表只按 id/task_id 查，grep 证据） | ❌ **移除 ×2**（stock_name 尤其无意义：展示字段） |
| task_result_summary_index | `uk(task_result_id, model_key)` | upsert 定位 | **保留** |
| task_result_summary_index | `idx_result_summary_type_stock_best(task_type,stock_code,is_best)` | stock 汇总 `model_summary_service.py:1477+` | **保留** |
| task_result_summary_index | `idx_result_summary_task_best(task_id,is_best)` | `filter_by(task_id)` / 按任务删除 | **保留** |
| task_result_summary_index | `idx_result_summary_type_market_best(task_type,market_type,is_best)` | 市场过滤组合 | **保留** |
| task_result_summary_index | `idx_result_summary_created_at` | 缓存/清理 `backtest_repository.py:75` `created_at < cutoff` | **保留** |
| task_result_summary_index | `idx_result_summary_period_key` | `period_key ==` 过滤 | **保留** |
| task_result_summary_index | `idx_result_summary_best_metric(best_metric_value)` | 范围过滤 `best_metric_value > min`（`model_summary_service.py:1486`）；作排序第 2 键（第 1 键是 `func.date()` 函数，索引本就无法整体服务排序） | **保留**（有 range 过滤实据） |
| task_result_summary_index | `idx_result_summary_result_timestamp`（ix_result_timestamp） | 日期范围过滤（:1493-1502） | **保留** |
| task_result_summary_index | `ix_..._is_best`（单列布尔） | 3 个复合索引的后缀；单列 is_best 过滤不存在（stock 汇总必带 task_type/market） | ❌ **移除** |

### 2.2 小表（语义纠偏为主）

| 表 | 索引 | 证据 | 判定 |
|---|---|---|---|
| backtest_product_result_cache | `uk(batch_id, cache_key)` | 查询命中 | **保留** |
| backtest_sheet_run_locks | `uk(spreadsheet_id)`、`ix_task_id` | 锁获取/释放 | **保留** |
| google_sheet | `uk(spreadsheet_id, registry_scope)` | 唯一性 + `spreadsheet_id` 等值查询的左前缀 | **保留** |
| google_sheet | `ix_google_sheet_spreadsheet_id` | **与 uk 左前缀完全冗余** | ❌ **移除** |
| google_sheet | `idx_active_in_use(is_active,is_in_use)` | 占用查询组合过滤 | **保留** |
| google_sheet | `ix_is_in_use`（单列布尔） | 无单列查询 | ❌ **移除** |
| google_sheet | `ix_table_type` / `ix_current_task_id` | `filter_by(table_type)`、释放占用 `registry_service.py:137` | **保留** |
| google_sheet | `ix_name` | 仅 `ORDER BY name`（百行表排序无意义） | ❌ **移除** |
| google_sheet_tokens | `idx_active_usage(is_active,current_in_use_count)` | 选占 `token_service.py:330-334`：filter(is_active,task_type) ORDER(current_in_use_count,...)——部分可用 | **保留**（可选优化：改 `(task_type,is_active,current_in_use_count)`，见 §6） |
| google_sheet_tokens | `ix_task_type` | 选占过滤 | **保留** |
| google_sheet_tokens | `ix_name` | 无按 name 查询 | ❌ **移除** |
| navigation_menu_items | `idx_parent_sort(parent_key,sort_order)` | 实际查询是全局 `ORDER BY sort_order,id` + Python 层按 parent 分组（`navigation_repository.py:17-26`），前缀用不上 | ❌ **移除**（表 <100 行） |
| navigation_menu_items | `ix_is_visible` | 布尔 + 微型表 | ❌ **移除** |
| scheduled_tasks | `ix_name` | 无按 name 查询 | ❌ **移除** |
| scheduled_tasks | `ix_is_active`（布尔） | `find_due` 是组合条件 | ❌ **移除** |
| scheduled_tasks | `ix_created_at` | 列表排序，微型表 | ❌ **移除** |
| RBAC 三表 + 关联表 | 仅 unique（username/role.code/permission.code）+ 复合主键 | 等值查询全命中 | ✅ 无需动 |
| system_config / stock_metadata / task_templates | `uk(key)`、`uk(stock_code,market_type)`、无附加 | upsert/查询命中 | ✅（stock_metadata 的 `ORDER BY updated_at` 在 uk 唯一性下至多排 1 行，见 `03` §5.3） |

## 3. 移除清单汇总（12 个确定 + 2 个随批）

| 表 | 索引 | 移除理由 | 附加动作 |
|---|---|---|---|
| task_results | `idx_success_timestamp` | 无组合查询 | — |
| task_results | `ix_task_results_return_series_id` | 零引用 | **同步删 `startup.py:162` `_ensure_model_index` 调用 + models `index=True`** |
| task_results_return | `ix_..._stock_code`、`ix_..._stock_name` | 零引用 + models `index=True` 摘除 | — |
| task_result_summary_index | `ix_..._is_best` | 布尔后缀冗余 | models `is_best` 的 `index=True` 摘除 |
| google_sheet | `ix_spreadsheet_id`、`ix_is_in_use`、`ix_name` | uk 前缀冗余 / 布尔 / 排序微表 | models `index=True` 摘除 |
| google_sheet_tokens | `ix_name` | 零引用 | — |
| scheduled_tasks | `ix_name`、`ix_is_active`、`ix_created_at` | 零引用 / 布尔 / 微表 | models `index=True` 摘除 |
| navigation_menu_items | `idx_parent_sort`、`ix_is_visible` | 查询形态不匹配 + 微表 | **同步删 `startup.py:357-358` 两行 `_ensure_model_index` 补建调用**（校准 2026-09-05：审计时漏列，实测存在） |

## 4. 误删需补回（20260811 的反向偏差）

| 表 | 索引 | 误删证据 |
|---|---|---|
| scheduled_tasks | `(is_active, next_run_time)`（原名 `idx_active_next_run`） | `find_due`（`scheduled_task_repository.py:50-61`）：`is_active AND is_running=false AND next_run_time<=now ORDER BY next_run_time`——调度 worker 每个 tick 执行的热路径，恰在 20260811 被删；现全表扫描 |
| backtest_product_result_cache | `(source_task_id)`（原名 `ix_backtest_product_result_cache_source_task_id`） | 缓存失效 `backtest_repository.py:113` `filter_by(source_task_id=task_id)` 在用；同名索引在 20260811 删除清单里 |

## 5. 新增/调整（可选，P3）

| 表 | 建议 | 依据 |
|---|---|---|
| tasks | `(task_type, created_at)` | `model_summary_service.py:1360` `filter(task_type=MODEL_SUMMARY_REBUILD).order_by(created_at.desc())`；现有 `idx_type_status` 无法服务该排序。任务类型基数小，收益取决于 rebuild 任务量 |
| google_sheet_tokens | `(task_type, is_active, current_in_use_count)` 替代 `idx_active_usage` | 选占查询三列精确匹配过滤+排序；token 池行数小，收益有限，仅在池扩容后考虑 |

## 6. MySQL/PostgreSQL 差异注意

| 事项 | MySQL | PostgreSQL |
|---|---|---|
| 移除索引 | `DROP INDEX` online（INPLACE，不阻塞 DML） | `DROP INDEX`（CREATE/DROP CONCURRENTLY 可免锁） |
| 布尔索引 | 低基数基本不选 | 同样不选；PG 另有 partial index 方案（`WHERE is_best`）可作 P3 备选，本项目无需 |
| utf8mb4 长度 | 现 uk 最长 `spreadsheet_id(255)+registry_scope(32)`≈1148B、`token_file(500)`≈2000B，均在 3072B 限内（DYNAMIC 行格式，MySQL 5.7+/8 默认）；若部署实例 ROW_FORMAT=COMPACT（767B 限）会建不起来——列入部署检查项 | 无此限制 |
| 表字符集/引擎 | models `__table_args__` 未显式 `mysql_engine/mysql_charset`，依赖服务器默认；建议在后续迁移统一声明 `InnoDB + utf8mb4`（与 `04` §3 联动） | 无 |

## 7. 迁移前验证命令（每项移除/补回各跑一次）

```sql
-- 1) 确认索引在现库存在
SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE() GROUP BY TABLE_NAME, INDEX_NAME;

-- 2) 确认优化器不选将被移除的索引（示例：success_timestamp）
EXPLAIN SELECT id FROM t_param_task_results WHERE success = 1 AND timestamp > '2026-01-01';

-- 3) 确认补回后 find_due 命中
EXPLAIN SELECT id FROM t_param_scheduled_tasks
WHERE is_active = 1 AND is_running = 0 AND next_run_time <= NOW();
```

迁移形态：一个迁移只做一组索引（移除 12+2 补回可拆两个），downgrade 按 20260811 先例**不回补陈旧定义**，仅注释说明依据。
