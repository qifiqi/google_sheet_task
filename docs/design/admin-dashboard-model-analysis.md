# 管理仪表盘模型展示分析

本文档是管理仪表盘数据选型的依据。统计数据必须遵守当前用户的任务类型权限与资源查看权限，接口不得返回 Token 原文、配置值、收益序列或用户隐私字段。

## 模型分级

| 模型 | 仪表盘用途 | 结论 |
| --- | --- | --- |
| `Task` | 任务总量、状态分布、趋势、运行中和最近任务 | 核心展示 |
| `TaskLog` | 最近 warning/error，帮助快速发现故障 | 核心展示，限制条数与文本长度 |
| `TaskResult` | 结果总量、成功数、失败数、成功率 | 核心展示 |
| `XplAnalysisJob` | 队列积压、执行中、完成、异常和平均计算耗时 | 核心展示 |
| `GoogleSheet` | 可用、占用和停用的 Sheet 资源 | 有 `google_sheet:view` 时展示 |
| `GoogleSheetToken` | Token 池可用数与当前占用量 | 有 `google_sheet:view` 时展示，不返回凭据 |
| `ScheduledTask` | 启用、运行中和下次执行时间 | 有 `scheduler:view` 时展示 |
| `BacktestSheetRunLock` | 当前回测 Sheet 锁数量 | 有 `backtest:view` 时展示 |
| `TaskTemplate` | 可用模板数量 | 有 `template:view` 时作为资产概览 |
| `TaskResultSummaryIndex` | 汇总索引和最优结果数量 | 有 `database:model_summary` 时作为资产概览 |
| `StockMetadata` | 股票元数据覆盖数量 | 有 `backtest:view` 时作为资产概览 |
| `TaskResultReturn` | 原始收益序列，体积大且不适合总览聚合 | 不展示，仅详情图表使用 |
| `BacktestProductResultCache` | 内部缓存实现，不代表业务健康度 | 不展示 |
| `User` | 当前用户身份已由顶部用户区展示 | 不做全局统计 |
| `Role` / `Permission` | RBAC 配置，不属于任务运行态 | 不展示 |
| `SystemConfig` | 可能包含敏感运行配置 | 不展示 |
| `NavigationMenuItem` | 驱动权限侧边栏和全局搜索 | 不作为指标展示 |

## 接口分区

`GET /admin/api/dashboard/overview` 返回以下稳定分区：

- `summary`：任务主状态 KPI。
- `daily_trend`：近 7 天创建与完成趋势。
- `execution_health`：任务结果与 XPL 队列健康度。
- `resource_health`：按权限返回 Sheet、Token、调度、锁和资产数据。
- `recent_tasks` / `active_tasks`：轻量任务摘要，不加载结果明细和日志集合。
- `recent_alerts`：当前账号可见任务的最近 warning/error。

仪表盘禁止调用完整任务序列化流程，避免为每条最近任务额外查询结果、XPL Job 和日志造成 N+1 查询。
