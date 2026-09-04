# 当前 stock_sdk 迁移边界

## 目标与约束

业务数据优先通过 `app/repositories` → `stock_sdk` 访问远程服务。本仓库不修改、不生成 `stock_sdk`，且不得通过通用分页拉取全量记录后在 Flask 侧做业务筛选。

本轮已移除不再被生产代码直接访问的业务 ORM 模型：结果收益序列、回测缓存与锁、结果汇总索引、股票元数据、任务模板、系统配置、Google Sheet 注册、计划任务和已废弃的 Token 模型。用户、RBAC、权限、导航菜单，以及仍有明确本地 SQL 使用场景的 `Task`、`TaskLog`、`TaskResult` 保留。

## 已可使用当前 SDK 完成的访问

| 场景 | Repository | 约束 |
| --- | --- | --- |
| 单任务结果分页 | `TaskResultRepository.list_results(task_ids=[task_id])` | SDK 仅支持单字段排序。 |
| 单任务全部结果读取 | `TaskResultRepository.list_task_results(task_id)` | 仅分页读取该任务，最大 10,000 条。 |
| 指定结果读取 | `TaskResultRepository.get_task_results_by_ids(task_id, ids)` | 单次最多 500 个 ID，并逐条验证所属任务。 |
| 单任务最近日志 | `TaskLogRepository.list_logs(task_id=...)` | 最多读取调用方限定的条数。 |
| 单条任务/结果详情 | `TaskRepository.get` / `TaskResultRepository.get` | 使用远程主键查询。 |

`list_task_results()` 不调用通用 `list_all()`；当远程返回的数据超过安全上限时会显式失败，避免异常任务触发无界读取。

## 当前 SDK 不能安全替代的本地访问

以下场景继续保留本地数据库实现，不能以客户端全量分页或本地拼接替代：

1. 任务列表统计、成功率、平均耗时和仪表盘聚合。
2. 未指定 `task_id` 的结果列表：它需要按关联任务类型做服务端权限过滤。
3. 按时间阈值批量清理 `TaskLog`、`TaskResult` 及其关联数据。
4. 数据库监控、索引检查和通用 SQLAlchemy 优化工具。
5. `xpl_analysis_jobs` 历史表的动态探测及关联删除。
6. DingTalk 的精确任务名检索与多字段排序。

任务看门狗已停用：当前 SDK 没有提供看门狗候选筛选、最近日志聚合和可重启原因所需的服务端查询能力。

## 若要完全移除 Task / TaskLog / TaskResult 本地表，需要补充的远程能力

- `TaskResult`：`task_id + result_ids` 联合查询、字段投影、复合排序、任务级统计、按时间范围清理。
- `TaskLog`：按时间范围查询和按保留期批量删除。
- `Task`：服务端统计/仪表盘聚合、精确名称检索和复合排序。
- 结果查询：按关联任务类型的服务端权限过滤。
- XPL：按任务、结果和收益序列关联删除。

在这些能力进入远程服务并重新生成 SDK 前，禁止以扩大分页大小、循环扫描远程全表或前端传入全部任务 ID 的方式绕过缺口。
