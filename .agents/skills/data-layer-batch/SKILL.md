---
name: data-layer-batch
description: 执行、验证或收尾 google_sheet_task 数据层重构的单个批次（P1-3/P1-1/B0/B1/B2/B3/B4/B5/P1-2）。当用户提到"数据层重构"、"执行批次"、"进批"、"B0/B1/B2/B3/B4/B5 批次"、"repository 层替换"、"收尾验证"或要求按 docs/design/data-layer-refactor 交付某一批时使用——即使没有明说"批次"二字，只要是在做数据层/repository/统一响应信封相关改造的验收与提交，也应触发。
---

# 数据层重构 · 单批次执行循环

本仓库的数据层重构设计已定稿于 `docs/design/data-layer-refactor/`（6 份文档 + EXECUTION_PROMPT.md）。
**文档是唯一事实源，本技能不复制设计内容**，只强制执行"每批完成动作"的固定顺序，防止步骤遗漏。

## 开工前（每个会话一次）

1. 通读 `docs/design/data-layer-refactor/EXECUTION_PROMPT.md`（红线与关键契约）。
2. 重读该批对应的两份文档：`01-db-inventory.md`（本批文件清点）+ `02-repository-design.md`（repository 方法契约）。
3. 检查 `03-execution-checklist.md` 文末"执行记录"表：确认上一批已登记、当前批未被做过（避免重复执行）。

## 批次循环（严格按序，缺一步不算完成）

### 1. 实现

- 替换 = 数据层迁移 + try/except 样板移除 + `api_response` 采用 + 前端读取/集成测试断言同步，**一次做完**，不留半成品。
- 行号偏移以实际代码为准；文档与代码冲突时，以调用点实际行为为契约反向补齐 repository 方法（不得改变调用方行为），并准备登记偏差。
- Windows 下 PowerShell 读中文文件需显式 UTF-8；本会话 shell 是 Git Bash，`pytest` 用 `python -m pytest`。

### 2. 验证（全过才可提交）

```bash
# 全量测试。门槛解释：passed 且无"新增"失败即通过——
# 3 个存量失败已在 03 执行记录表登记为基线豁免（kline×2 + ISO 日期×1），
# 这 3 个若仍失败不阻塞；出现任何其他失败 = 阻塞，必须修复后重跑。
python -m pytest -q tests/unit tests/integration --disable-warnings

# 该批的 grep 验证（命令见 03 对应批次小节），例如 B1 收尾：
grep -rEn "db\.session|\.query\." app/routes --include="*.py"     # 应为空
grep -rn '"status": "error"' app/routes --include="*.py"          # 应为 0
```

### 3. 提交（单批一提交）

- `git add` **只加本批涉及的明确路径**。禁止 `git add -A` / `git add .`——工作区可能存在与本重构无关的未提交变更（如 `.codex/` 删除），绝不能混入批次提交。
- 提交信息用中文 conventional 格式，注明批次号（如 `refactor(data-layer): B1 路由层替换 template_api/auth_api`）。
- 回滚 = `git revert` 该批单个提交；B3/B4 单文件语义风险可单独回退并在执行记录标注豁免。

### 4. 登记（必须，是批次的最后一步）

在 `03-execution-checklist.md` 文末"执行记录"表追加一行：日期 / 批次·文件 / 结果 / 偏差与说明。
偏差（文档行号漂移、契约补齐、豁免）在此登记后，才算本批闭环。

## 红线速记（详情以 EXECUTION_PROMPT.md 为准）

- 不改 URL/请求结构/HTTP 状态码；响应业务键整体移入 `data`，前端与集成测试同批更新；
- 事务 commit 粒度不变（断点续跑语义）；写方法带 `commit: bool = True`，异常 `_rollback()` 后裸 `raise`（禁止 `raise e`）；读方法绝不 commit；
- 不涉及任何数据库修改：不改 schema、不写迁移、不动表数据；
- 无兼容层：不留旧格式分支、无灰度/回退开关、无双轨 API；
- repositories 禁 import `app.services`/`app.routes`/Flask；routes/services 禁 ORM（import 模型枚举常量允许）；
- 任务线程域异常（`C5*`、`RetryableNetworkTaskError`、`[NETWORK_RETRYABLE]`）不并入统一异常体系；
- 范围外不动：`app/startup.py`、`run.py`、`app/navigation.py`、`migrations/`、`tests/`、`scripts/`、`utils/db_monitor.py`、`utils/db_optimizer.py`。

## 批次顺序与前置

P1-3（最先，独立小改）→ B0（纯新增）→ B1 路由 → B2 常规服务 → B3 任务执行核心 → B4 执行链与报表 → B5 外围收尾 → P1-2 池化（**前置 B3 完成**）。
P1-2 的执行细节另见 `05-task-runtime-pooling.md`。
