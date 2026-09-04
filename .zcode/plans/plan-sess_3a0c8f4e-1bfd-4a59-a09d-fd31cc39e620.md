目标是仅基于当前 `stock_sdk` 的现有能力收缩本仓库的直连数据库访问；不修改、生成或扩展 `stock_sdk`，不改造仪表盘后端，也不重构看门狗逻辑（看门狗改为明确停用/注释）。用户、角色、权限和导航菜单保持本地数据库实现。

## 已确认的可行边界

当前 SDK 对 `Task`、`TaskLog`、`TaskResult` 提供通用分页、按 ID 读取、保存和删除；现有 Repository 已封装其中大部分能力：

- 任务：可按状态、任务类型、关键字、创建起点分页。
- 日志：可按 `task_id` 分页、按时间单字段排序。
- 结果：可按 `task_ids`、`success` 分页、按单字段排序。

因此，本轮会迁移所有可由**服务端已有筛选条件 + 有界分页/定向 ID 请求**正确完成的访问；不会以 SDK 全量分页后在客户端筛选的方式替代 SQL。

## 实施步骤

1. **建立迁移清单与保护测试**
   - 为 `TaskResultRepository.list_results`、`TaskLogRepository.list_logs` 补充/完善单元测试，断言调用当前 SDK 时携带 `task_ids`、`success`、`task_id`、分页和排序字段。
   - 为迁移的服务及路由使用 fake Repository/SDK 响应测试，确保不再调用 `Model.query` 或 `db.session`。
   - 保留现有数据库集成测试中仍被未迁移场景使用的夹具，不把测试改造成 SDK 全表扫描。

2. **迁移当前 SDK 已充分覆盖的定向查询**
   - 把任务运行态页面的最近日志读取迁移到 `TaskLogRepository.list_logs(task_id=..., page_size=..., timestamp desc)`，在展示层按需反转为时间正序。
   - 把 `task/logs.py` 的按任务最近日志读取迁移到同一 Repository。
   - 把任务状态查询中的“最新结果”迁移到 `TaskResultRepository.list_results(task_ids=[...], page_size=1, timestamp desc)`。
   - 将回测训练及多品回测的**单任务、分页**结果列表迁移到 `TaskResultRepository.list_results(task_ids=[...])`；保持 SDK 返回的远端分页总数。
   - 将模板结果的单条查看/删除改为 `TaskResultRepository.get(result_id)` → `TaskRepository.get(task_id)` 完成授权上下文读取 → `TaskResultRepository.delete(result_id)`；避免本地 SQL join。
   - 将 DingTalk 中按任务 ID 查询、按状态分页列举/重启的 Task 查询改为 `TaskRepository.get` / `list_tasks`。对于依赖精确名称匹配或复合排序的分支，保留本地实现或返回受控“不支持”的结果，不用模糊 `keyword` 冒充精确查找。

3. **迁移单任务结果读取的业务服务，设置有界策略**
   - 把回测训练全局预览、导出、断点恢复、多品回测预览、运行态结果统计等“单个 task_id 的结果读取”改为 Repository 的远端分页读取。
   - 提取一个仅遍历**指定 task_id**远端分页结果的内部 helper；它严格根据远端 `has_next/total` 停止，不调用通用 `list_all`，并设置合理的分页上限与异常提示。
   - 在需要 `result_ids` 精确子集的路径中，仅当调用方提交的 ID 数量在既有业务上限内时逐条 `GetInfoById` 并验证 `task_id`；否则明确拒绝并说明当前远端 SDK 不支持批量结果 ID 查询。不会下载任务外的结果或全库结果。
   - 接受并测试当前 SDK 的限制：结果分页只能请求单排序字段，无法保证原 SQL 的 `step_index, timestamp, id` 三字段跨页稳定排序；迁移后采用服务端可支持的单字段排序，并在接口说明/测试中固化该兼容边界。

4. **停用看门狗**
   - 在启动注册和运行入口处明确禁用任务看门狗；将看门狗触发/初始化代码注释或移除，并保留清楚的停用说明，确保不再执行其本地 SQL 任务/日志筛选。
   - 不对 `app/services/task_watchdog.py` 内部查询与恢复策略做功能性改造。
   - 更新相关测试，使其验证看门狗不会注册/启动，而不是继续依赖本地 SQL 候选筛选。

5. **不处理仪表盘后端与当前无法用 SDK 正确替代的场景**
   下列保持原状，并在代码中保留或补充清晰的“当前 SDK 能力不足”边界说明：
   - `TaskQueryService` 的任务列表统计、成功率、平均耗时等聚合；
   - `template_api` 未指定 `task_id` 时按任务类型权限过滤的全局结果列表；
   - 定时任务/worker 按时间阈值批量清理 `TaskLog`、`TaskResult`；
   - `db_monitor`、`db_optimizer`、通用 SQLAlchemy 工具；
   - `xpl_analysis_jobs` 的动态表检测和关联删除；
   - DingTalk 精确任务名和复合排序查询。

   它们的缺口会整理为仓库内的迁移边界说明：当前 SDK 缺少结果 ID 集合/字段投影/多字段排序、时间范围删除、任务类型 join 过滤、服务端统计及 XPL API。不会改 SDK，也不会用客户端全量扫描绕过这些限制。

6. **移除已完全迁移的非身份业务 ORM 模型和遗留 DDL**
   - 删除已没有直接 ORM 访问的模型：`TaskResultReturn`、`BacktestProductResultCache`、`BacktestSheetRunLock`、`TaskResultSummaryIndex`、`StockMetadata`、`TaskTemplate`、`SystemConfig`、`GoogleSheet`、`ScheduledTask`，以及已禁用的 `GoogleSheetToken` 历史块。
   - 将仍被 SDK Repository 使用的枚举及 `google_sheet_registry_scope` 从 `models.py` 移到独立 domain/constants 模块，更新调用方。
   - 删除上述模型对应的启动期 schema 修补、shell context 暴露和无效 ORM imports；保留 `Task`、`TaskLog`、`TaskResult` 及用户/RBAC/导航模型和必要的本地 schema 支持。
   - 不移除 Flask-SQLAlchemy / Flask-Migrate，因为剩余的本地任务统计、清理、身份与菜单仍依赖它们。

7. **验证与质量检查**
   - 运行仓库标准结构回归：`pytest tests/test/test_p0_p1_refactor.py`，并运行涉及变更的回测、模板结果、调度、启动与看门狗定向测试。
   - 对所有生产目录执行一次 direct-ORM 搜索，输出剩余访问点并核对它们均属于用户/RBAC/导航、仪表盘、保留期清理、监控/优化、XPL 兼容，或明确记录的 SDK 缺口。
   - 使用代码审查检查迁移后的错误处理、分页边界、远端 DTO 兼容性及没有意外保留业务模型导入。

## 当前 SDK 仍无法满足、如未来需要彻底移除本地 Task/Result/Log 数据库时必须补的接口

- `TaskResult`：按 `task_id + result_ids` 查询、字段投影、复合排序、任务级计数/最新记录、按时间范围清理；
- `TaskLog`：时间范围查询和按保留期服务端批量删除；
- `Task`：服务端统计/仪表盘聚合、按精确名称及复合排序查询；
- 结果列表：按关联 Task 类型进行服务端授权过滤；
- XPL：支持按 task/result/return 系列关联删除的 API。

这些结论来自现有 Repository 与 SDK DTO：`app/repositories/task_repository.py:73-101`、`app/repositories/task_result_repository.py:17-39`、`app/repositories/task_log_repository.py:13-36`。