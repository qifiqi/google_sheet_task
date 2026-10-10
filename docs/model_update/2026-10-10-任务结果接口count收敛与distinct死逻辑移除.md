# 任务结果接口 count 收敛与 distinct 死逻辑移除

日期：2026-10-10
分支：dev_vue
关联症状：任务详情页结果 tab（`/api/tasks/<id>/results`）与结果查询页（`/api/results`）翻页响应慢。

## 背景

对本地 1.8GB SQLite 快照（`task_results` 36.9 万行 / 973 任务 / 单任务最多 6600 行）逐条 SQL 实测定位：

- 任务详情页每页请求实际执行 **5 条 count 类 SQL**：repository `list_by_task_paginated` 内部 paginate count + `count_by_task_success`（成功/失败拆 2 条），service `get_task_results` 分支又把 `count_by_task_success` **重复调用了一遍**。实测 5 条合计 945.6ms，比当页数据读取（173ms）慢一个量级。
- 结果查询页每页执行 distinct task_type 子查询 + paginate count + success/failed 聚合共 3 条，实测 401.3ms；其中 distinct task_type 过滤是**恒真条件**（join Task 后行必属于某个已存在类型），属死逻辑。
- `result` 大 JSON 的 `json.loads` 仅 0.1ms/10 行、当页数据读取 173ms——**不是**主要瓶颈。

## 修改内容

### `app/repositories/task_result_repository.py`

1. `count_by_task_success`：成功/失败两条独立 `filter_by(...).count()` 合并为一条 `case when` 聚合，返回形状 `{"total_success", "total_failed"}` 不变。
2. `list_by_task_paginated`：total/success/failed 合并为一条聚合；取页由 `paginate()` 改为 `offset/limit`（flask-sqlalchemy 3.1 的 `Query.paginate` 不支持外传 total，`count=False` 时 total 恒为 None）。返回键（items/total/pages/current_page/per_page/total_success/total_failed）与分页语义（per_page≤100、page≥1、空表 pages=0）逐值对齐。
3. `list_paginated`：删除 distinct task_type 死逻辑分支（join Task 本身已限定存在结果的任务；`Task.task_type` 有 default 且库内无 NULL，结果集不变）；total 并入 success/failed 同一条聚合，取页改 offset/limit。返回形状不变（本方法本就不含 pages 键，/results route 自行计算）。

### `app/services/task/results.py`

`get_task_results` 分页分支删除重复的 `count_by_task_success` 调用，直接透传 `list_by_task_paginated` 结果（该方法已含全部计数字段）。

## 收敛效果（实测，旧库最大任务 6600 行）

| 路径 | 修改前 | 修改后 |
|---|---|---|
| 任务详情页 count 类 SQL | 5 条，945.6ms | 1 条，156.7ms（-83%） |
| 结果查询页 distinct+聚合 | 3 条，401.3ms | 1 条，212.9ms（-47%） |

生产库为远程 MySQL 时，串行 SQL 条数减少同时节省每条的网络往返，收益比例更大。

## 明确不做：任务详情页列表裁剪 result / 懒加载

评估过"列表不带 result、点更多再拉详情"（`list_by_task_fields` 白名单投影）：

- C4/C5/C7 的 `ResultGroupsCards.vue` 卡片视图**直接消费每行 result** 构建指标列（`versionShared.buildVersionResultGroups`），裁剪会直接破坏功能；
- C3 表格"执行结果"列内联摘要即用户要看的内容；
- 实测数据读取仅 173ms/页，收益配不上交互变更。

结果查询页（admin/Results.vue）本就是"列表 substr 预览 + 点详情单条拉取"模式，无需改动。

## 验证

- `pytest tests/unit/test_repositories.py tests/integration/test_template_result_api.py`：36 passed。
- 全量回归 `pytest tests/unit tests/integration`：796 passed / 24 failed / 10 skipped；24 个失败经 git stash 基线比对确认为**既有失败**（golden projection / date parser / global preview 等区域），与本次改动无关。

## 遗留提醒（超出本次范围，未动）

- 仓库红线"不修改数据库 schema/迁移/数据"，本次不含任何迁移。但实测快照库 `task_results` 仅有 `return_series_id` 一个索引（旧 schema），当前模型定义的 `idx_task_step (task_id, step_index)`、`idx_task_results_task_timestamp (task_id, timestamp)`、timestamp 单列索引依赖建库时 `create_all`/migrations 生成；`app/startup.py` 的 schema 修补只补列不补索引。**线上库若早于这些索引初始化，任务详情页的 task_id 过滤会退化为全表扫描**，慢会被数量级放大，需 DBA 核实线上索引状态。
- `/api/results` keyword 搜索 `ilike '%kw%'` 无法走普通索引，大表上是全表扫描；如后续仍慢可考虑全文索引或前缀匹配收窄。
