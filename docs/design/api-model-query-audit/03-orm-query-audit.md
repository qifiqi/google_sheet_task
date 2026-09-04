# 03 — ORM 查询审计

> 范围：`app/repositories/`（14 文件）+ services 层 ORM 使用点。总体结论：B0~B3 数据层重构后查询纪律良好（分页统一 `paginate(error_out=False)`、投影 `with_entities/load_only` 有意识使用、批量删除统一 `synchronize_session=False`、无 N+1 重灾区），剩余问题按影响排序如下。

## 1. 问题总表

| # | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| 3.1 | **P1** | `google_sheet_token_service.py:26` | `Task.query.filter_by(status='running').all()` 整行加载，含 `config` TEXT（单任务配置可达数十 KB） | 改 `with_entities(Task.id, Task.task_type)`——调用方（token 占用联动）只消费这两个字段 |
| 3.2 | **P2** | `google_sheet_token_service.py:67` | `GoogleSheetToken.query.all()` 整行加载，含 `token_context` TEXT（token JSON 原文） | 快照场景改 `with_entities(GoogleSheetToken.id, .current_in_use_count, .max_usage_count, .is_active)` |
| 3.3 | **P2** | `model_summary_service.py:1516-1526` | stock 汇总分支 `summary_query.all()` 全量取回 Python 层聚合（无 GROUP BY / LIMIT），summary 行数随任务线性增长 | 改 SQL `GROUP BY stock_code` 聚合（COUNT/MIN/MAX），或至少 `func.date` 分组下推 |
| 3.4 | P3 | `rbac_repository.py:88` 等 | `list_users/roles` 对每行 `to_dict()` 触发 `roles/permissions` lazy load（N+1）；表为百行级，实害小 | 列表接口加 `selectinload(User.roles)`；或维持现状并注释行数量级前提 |
| 3.5 | P3 | `task_result_repository.py:143-156` | `count_by_task_success` 两次 COUNT | 合并为一次 `GROUP BY success` 计数 |
| 3.6 | P3 | `stock_metadata_repository.py:18-30,53-60` | `uk(stock_code,market_type)` 保证至多一行，`ORDER BY updated_at DESC, id DESC + first()` 的排序永远排 1 行 | 去掉 ORDER BY 或注释说明保留原因（若担心历史脏数据多行） |
| 3.7 | P3 | `task_repository.py:49-57` | 关键字搜索 `ilike %kw%` 三字段前置通配，无法用索引 | **接受现状**（MySQL 下前置通配本就不可索引；表量级内可接受），不建全文索引 |
| 3.8 | P3 | `result_api` 底层 `task_result_repository.list_paginated` | 每次请求 `SELECT DISTINCT task_type`（全表） | 可接受；如需优化改走 `meta_api` 的枚举或加内存缓存 |

## 2. 重点项细节

### 3.1 / 3.2 token 占用链路大字段

调用频度：每次任务启动/停止/token 选占都会触发（执行链热路径）。`t_param_tasks.config` 与 `t_param_google_sheet_tokens.token_context` 均为 TEXT，`SELECT *` 使 MySQL 在行内/溢出页读取大字段后整行传输——改投影后单次查询字节数下降一个数量级以上。**注意**：改投影不影响 `is_available()` 等方法（它们只在整实体路径用）。

### 3.3 model_summary stock 聚合

`summary_query.all()` 把明细行拉回后由 `_summary_from_items` 内存聚合；summary_index 表是大表（每条结果 × 模型键一行）。改写要点：聚合列（现有 `_summary_from_items` 的统计口径）下推为 `func.count/min/max` + `GROUP BY stock_code`，分页明细查询保持现状。**改前先核对聚合口径与现输出逐字段一致**（`tests/unit/test_model_summary_service.py` 有 skip 用例待启用，见 AGENTS.md）。

## 3. 良好实践（保持，不要"优化"掉）

| 模式 | 位置 | 说明 |
|---|---|---|
| `bulk_create` 用 `add()` 循环而非 `bulk_save_objects` | `task_result_repository.py:231-236` | **必须保留**：模型层有 `before_insert` 事件（stock_code 标准化，`models.py:900-935`），bulk API 会绕过事件 |
| 删除统一 `synchronize_session=False` + 业务标识过滤 | `data_cleanup.py:30-66` | 20260810 去外键后按业务键级联清理，模式正确 |
| `populate_existing()` 强制刷新实体 | `task/runtime.py:146,324` | 任务线程与请求线程双访问场景的正确做法 |
| `paginate(error_out=False)` + per_page 上下限钳制 | 各 list_* | 统一信封分页契约 |
| 投影三列批量导出 | `task_result_repository.list_export_rows` | 明确注释了跳过 ~10KB kline 大字段的意图 |

## 4. 事务与提交纪律

- repositories 写方法默认方法内 commit、`commit=False` 可组合——抽查 `task_repository`、`task_result_repository`、`backtest_repository` 均符合 data-layer 02 章约定，无读路径 commit；
- `config.py:143-447` 的启动播种（`init_config`）直接使用 `SystemConfig.query`——属 `app/startup.py` 播种范围，数据层重构已豁免，不改。

## 5. 已核实的合规项（审计通过）

1. **参数绑定**：全库未发现 f-string/`%`/format 拼接 SQL；`rbac_repository.py:122,182,185` 的 `db.session.execute(delete(...).where(...))` 为 SQLAlchemy 表达式构造（列比较自动绑定），**合规**。此条列为不变红线：后续任何手写 SQL（如 3.3 的 GROUP BY）必须继续走绑定参数；
2. 时间窗口过滤压 SQL 层（watchdog 承诺）在 `task_repository`/`*_repository.delete_older_than` 落实；
3. 无 `get_or_404` 残留（HTTP 语义未渗入数据层，`scheduled_task_repository.py:41` docstring 即约定证据）。

## 6. 时间基准混用（登记，不随本批修）

`models.py` 中 `User.created_at` 用 `datetime.utcnow`（:58），其余全部 `datetime.now`（本地时间）——同一 MySQL 库两种时间口径并存（PG 的 `timestamptz` 会放大该问题）。涉及数据语义修正（存量为本地时间），**单独立项**，本审计仅登记：统一方向建议 `datetime.now`（与现状大多数列一致 + 前端 ISO 直显），迁移时对 `t_param_user.created_at/last_login` 做一次性 +8h 修正需先确认部署时区。
