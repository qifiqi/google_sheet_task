# 当前 stock_sdk 迁移边界

## 目标与约束

业务数据优先通过 `app/repositories` → `stock_sdk` 访问远程服务。本仓库不修改、不生成 `stock_sdk`，且不得通过通用分页拉取全量记录后在 Flask 侧做业务筛选。

本轮已移除不再被生产代码直接访问的业务 ORM 模型：结果收益序列、回测缓存与锁、结果汇总索引、股票元数据、任务模板、系统配置、Google Sheet 注册、计划任务和已废弃的 Token 模型。用户、RBAC、权限、导航菜单，以及仍有明确本地 SQL 使用场景的 `Task`、`TaskLog`、`TaskResult` 保留。

## 已可使用当前 SDK 完成的访问

| 场景 | Repository | 约束 |
| --- | --- | --- |
| 单任务结果分页 | `TaskResultRepository.list_results(task_ids=[task_id])` | SDK 仅支持单字段排序。 |
| 全局结果分页（后台结果页） | `TaskResultRepository.list_results(...)` | 有 `task_id` 时按任务过滤；未传时按时间倒序分页，不做任务类型权限关联过滤。 |
| 单任务全部结果读取 | `TaskResultRepository.list_task_results(task_id)` | 仅分页读取该任务，最大 10,000 条。 |
| 指定结果读取 | `TaskResultRepository.get_task_results_by_ids(task_id, ids)` | 单次最多 500 个 ID，并逐条验证所属任务。 |
| 单任务最近日志 | `TaskLogRepository.list_logs(task_id=...)` | 最多读取调用方限定的条数。 |
| 单条任务/结果详情 | `TaskRepository.get` / `TaskResultRepository.get` | 使用远程主键查询。 |
| DingTalk 任务读取 | `TaskRepository.get` / `TaskRepository.list_tasks(statuses=...)` | 按状态过滤与分页由服务端完成；仅支持单字段排序。 |
| DingTalk 任务名解析 | `TaskRepository.list_tasks(keyword=...)` + 本地精确比对 | SDK 无精确名称匹配；用 keyword 缩小范围后本地过滤同名任务。 |
| 任务通知 | 远程任务记录 | 告警不再读取本地用户表和手机号，用户/@ 相关代码已注释停用。 |

`list_task_results()` 不调用通用 `list_all()`；当远程返回的数据超过安全上限时会显式失败，避免异常任务触发无界读取。

## 当前 SDK 不能安全替代的本地访问

以下场景已按要求停用本地数据库读取，改为返回假数据（原逻辑注释保留）：

1. 管理后台仪表盘聚合（`/api/dashboard/overview`、任务运行态结果摘要与最近日志、任务列表统计）：SDK 无聚合接口，直接返回全零/空假数据。
2. 数据库监控接口（`/database/status`、`/database/vacuum`、`/database/suggestions`）：`db_monitor` 的本地探查已注释，接口返回假数据。
3. `db_optimizer`：无接口且无调用方，整文件注释停用。

任务看门狗已停用：需要看门狗候选筛选、最近日志聚合和可重启原因所需的服务端查询能力。

已删除的能力（不再保留本地实现，等待远程服务补充后按需重建）：

- 按时间阈值批量清理 `TaskLog`、`TaskResult` 的定时任务（`cleanup_old_logs` / `cleanup_old_results` / `cleanup_old_data` 已移除，历史定时记录会被跳过并告警）。
- `xpl_analysis_jobs` 历史表的动态探测及按任务/结果/收益序列的关联删除。
- 钉钉告警的用户与手机号逻辑（值班开发 @、创建人展示，已注释停用）。

## 若要完全移除 Task / TaskLog / TaskResult 本地表，需要补充的远程能力

- `TaskResult`：字段投影、复合排序、任务级统计、按时间范围清理。
- `TaskLog`：按时间范围查询和按保留期批量删除。
- `Task`：服务端统计/仪表盘聚合。
- XPL：按任务、结果和收益序列关联删除（若仍需重建历史清理能力）。

在这些能力进入远程服务并重新生成 SDK 前，禁止以扩大分页大小、循环扫描远程全表或前端传入全部任务 ID 的方式绕过缺口。
