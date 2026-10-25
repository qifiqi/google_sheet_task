# docs/ 文档索引（唯一入口）

> 治理原则：**同一内容只有一个权威来源**。本索引是全部文档的唯一入口；治理动作与全量基线见 [project-memory/文档台账.md](project-memory/文档台账.md)；大纲见仓库根目录 [文档大纲](../文档大纲.md)。
> 最近治理：**2026-10-15**——"已实现实况"与"设计方案"分离；已收官设计主题归档至 `archive/`，design/ 原位留跳转存根。

## 目录结构

```
docs/
├── README.md            本索引（唯一入口）
├── project-memory/      项目记忆：当前实现实况 + 决策 + 问题（权威来源）
├── guides/              操作指南（how-to）
├── design/              设计文档：仅 partial/pending（未完成事项的工作现场）
│                        已归档主题在此留一行跳转存根（兼容历史引用）
├── archive/             已实现的设计文档与退役文档（只读查阅，不再维护）
├── model_update/        变更记录：每次大规模修改一篇（AGENTS.md 红线，只增不删）
└── release-notes/       面向用户的发布说明与周报快照
```

## 状态约定

- design/ 主题文档头部标注 status：
  - **implemented**：已全部落地 → 整体归档至 `archive/design/`；
  - **partial**：部分实现 → 留在 `design/`，文档内标注已实现/未实现部分；
  - **pending**：未实现 → 留在 `design/`。
- `model_update/` 新增变更文档后，在 [project-memory/变更日志.md](project-memory/变更日志.md) 对应月份追加一行。

## project-memory/（当前实现实况——权威来源）

| 文件 | 对应职责 | 说明 |
|---|---|---|
| [架构总览.md](project-memory/架构总览.md) | architecture | 技术栈 / 启动流 / 扩容约束（含 2026-10-15 勘误注记） |
| [数据库模型.md](project-memory/数据库模型.md) | modules | 17 个模型 / 建库路径 / SQL 修复存档 |
| [GoogleSheet执行链路.md](project-memory/GoogleSheet执行链路.md) | — | Sheet IO / Token 池 / C 系执行器 / 东财 K 线 |
| [任务系统与调度.md](project-memory/任务系统与调度.md) | — | 任务门面 / 状态机 / 断点恢复 / 看门狗 / 调度 |
| [回测系统与报告.md](project-memory/回测系统与报告.md) | — | 单多品回测 / 全局预览 / 绩效分析 / Word 导出 |
| [接口总览.md](project-memory/接口总览.md) | — | 蓝图与端点清单、URL 收敛对照 |
| [策略回测报告参数与指标公式.md](project-memory/策略回测报告参数与指标公式.md) | — | Word 报告参数 / 版式 / 六图 / 指标公式手册 |
| [技术决策.md](project-memory/技术决策.md) | decisions | 技术决策登记册（决策 + 理由 + 出处） |
| [变更日志.md](project-memory/变更日志.md) | changelog | 变更摘要，详情指向 model_update/ 原文 |
| [已知问题.md](project-memory/已知问题.md) | known-issues | 未解决问题 / 代码风险 / 文档-代码漂移登记 |
| [文档台账.md](project-memory/文档台账.md) | ledger | 治理记录 + 全量文档 sha256 基线（增量治理依据） |

## guides/（操作指南）

- [本地开发指南.md](guides/本地开发指南.md) — 环境变量 / 启动 / CLI / 测试 / Windows 编码
- [登录与鉴权指南.md](guides/登录与鉴权指南.md) — JWT 双 token / token_version / RBAC 现状
- [部署运维.md](guides/部署运维.md) — Docker / gunicorn / Nginx / 配置体系 / 运维检查单
- [策略回测报告模板使用说明.md](guides/策略回测报告模板使用说明.md) — Word 报告请求结构与通用 Word JSON 协议

## design/（仅 partial/pending；已归档主题留跳转存根）

| 主题 | status | 摘要 |
|---|---|---|
| [backtest-unify-2026-09](design/backtest-unify-2026-09/README.md) | partial | 无风险利率与 K 线指纹跳写已落地；全局预览统一 / Word 透出端点 / Token 去文件化 / Drive 登记未实施 |
| [ponytail-audit-2026-09](design/ponytail-audit-2026-09/01-审计报告.md) | partial | P01~P07/P10/P17 完成；P11 剩余、P12、P14 E4、P15 未完（跟踪表见 02 §4） |
| [deadcode-audit-2026-10](design/deadcode-audit-2026-10/README.md) | partial | 高置信删除与重复合并已执行；C4 get_bdl 合并、SDK 裁剪、分页双轨等未完 |
| [metrics-unify-2026-09](design/metrics-unify-2026-09/指标计算与单品多品统一方案.md) | partial | V1 引擎 / summary_contract 已统一；行号锚点漂移，验收章节为历史产物 |

存根（implemented，正文在 archive/）：api-model-query-audit、code-audit-2026-09、constants-audit-2026-09（2026-10-24 收官，10-25 归档）、data-layer-refactor、frontend-refactor、routes-restructure-2026-09、sso-integration-2026-09、mobile-adaptation-audit-2026-09、multi-index-word-report、performance-analysis-v3、vue-frontend-fix-2026-09。

## archive/（implemented，只读）

- `design/` 下 11 个已收官主题：api-model-query-audit、code-audit-2026-09、constants-audit-2026-09、data-layer-refactor、frontend-refactor、routes-restructure-2026-09、sso-integration-2026-09、mobile-adaptation-audit-2026-09、multi-index-word-report、performance-analysis-v3、vue-frontend-fix-2026-09
- 退役文档：[前端Vue工程.md](archive/前端Vue工程.md)（frontend/ 已移除，仅历史参考）、[目录索引.md](archive/目录索引.md)（被本 README 取代）

## model_update/ 与 release-notes/

- `model_update/`：按月归并的变更记录（每月一篇汇总，2026-10-16 起不再新增单篇），**大改必写**（AGENTS.md 红线）；入口见 [变更日志.md](project-memory/变更日志.md)。
- `release-notes/`：2026-09-15 发布说明与团队周报（历史快照）。

## 引用纪律

- 代码注释 / AGENTS.md 引用文档时用仓库绝对路径 `docs/...`；已归档主题用 `docs/archive/design/<主题>/`（design/ 存根保证旧路径仍可解析）。
- 不要在 project-memory 与 design/model_update 之间复制内容；摘要必须指向原文。
- 新增文档后同步更新本 README 与 `project-memory/文档台账.md`。
