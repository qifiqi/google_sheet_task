# 路由分层结构重构与文件重命名（2026-09）

目标：HTML 页面路由与 JSON API 路由单一归属——页面统一收敛到
`app/routes/pages/` 包，API 留在 `app/routes/` 平级；三层（接口层
routes / 业务层 services / 数据层 repositories）文件名形成可预测的规范。

## 1. 命名规范（后续新增文件遵循）

| 层 | 规则 | 示例 |
| --- | --- | --- |
| routes（接口层） | JSON API：`<域>_api.py`，蓝图名 `<域>_api_bp`；HTML 页面：`pages/<域>.py`，蓝图名可带 `_pages` 后缀（页面专属蓝图） | `task_api.py` / `pages/google_sheet.py` |
| services（业务层） | `<域>_service.py` 为主入口；包内拆分时入口收敛为 `service.py`/`facade`，内部模块按职责命名 | `backtest_report_query_service.py`、`performance_analysis/service.py` |
| repositories（数据层） | `<域>_repository.py`，方法前缀按 AGENTS.md 数据层约定（`get_/list_/create_/update_/append_...`） | `auth_repository.py` |

不变式：**URL 与蓝图 endpoint 名在重构中保持不变**（前端 fetch、
`url_for`、旧书签兼容均不受影响）。

## 2. 本次迁移/重命名映射

### routes：页面收敛到 `app/routes/pages/`

| 原位置 | 新位置 | 说明 |
| --- | --- | --- |
| `app/routes/page_files.py` | `app/routes/pages/__init__.py` | `send_page`/`register_page_routes` 助手成为包入口 |
| `app/routes/auth_pages.py` | `app/routes/pages/auth_pages.py` | 蓝图名 `auth_pages` 不变（`url_for('auth_pages.login_page')` 依赖）；新增 SSO 入口注释 |
| `app/routes/admin.py` | `app/routes/pages/admin.py` | |
| `app/routes/eastmoney_kline.py` | `app/routes/pages/eastmoney_kline.py` | |
| `app/routes/global_preview.py` | `app/routes/pages/global_preview.py` | |
| `app/routes/backtest_training.py` | `app/routes/pages/backtest_training.py` | bp + legacy_bp 均不变 |
| `app/routes/backtest_multi_product.py` | `app/routes/pages/backtest_multi_product.py` | 同上 |
| `app/routes/google_sheet.py` | `app/routes/pages/google_sheet.py` | create/detail 版本 dispatcher 保留手写 |
| `app/routes/performance_analysis.py` | 拆分为 `app/routes/pages/performance_analysis.py`（3 个页面，蓝图 `performance_analysis_pages_bp`）+ `app/routes/performance_analysis_api.py`（3 个 API） | 原文件页面/API 混居，是最后一个混合文件；API 蓝图名 `performance_analysis` 与 URL 前缀不变 |

### services：名实相符重命名

| 原位置 | 新位置 | 说明 |
| --- | --- | --- |
| `app/services/export_file_service.py` | `app/services/export_workbook_service.py` | 内容逐行不变（openpyxl Workbook/ZIP/CSV 构建器）；原文件名与 `export_service.py`（统一导出入口，含异步队列）无法区分谁是入口谁是构建器 |
| `app/services/sso_service.py` | 新增 | 主服务 SSO 换票（见 [sso-integration-2026-09](../sso-integration-2026-09/README.md)） |

### 此前已完成（本仓库相关提交，列为现状记录）

- `rbac_service.py → auth_service.py`、`rbac_repository.py → auth_repository.py`（d824869）
- xpl 页面/API 已整体迁入 `performance_analysis` 域（e87adca）

## 3. 评估后明确不改的部分

| 项 | 理由 |
| --- | --- |
| `backtest_api.py` 内 bt/bmp 双蓝图共存 | 文件头注明设计决定（两域 API 端点同构，拆分反而复制 import 面）；文件名 `backtest_api` 与内容相符 |
| `scheduler_service.py` vs `scheduled_task_worker.py` | 语义不同：前者为定时任务管理/编排服务，后者为到期任务执行 worker；非同义重复 |
| `strategy_backtest_report_charts.py`（无 `_service` 后缀） | 报表服务的图表构建 helper 模块，非独立业务入口 |
| `model_summary_service.py` + `model_summary/` 包、`performance_analysis/` 包内 `service.py` | 两种"门面 + 内部模块"形态并存；统一形态收益低于全量 import 改动成本，记录于此供后续域演进时靠拢 |
| repositories 层 | `rbac→auth` 重命名后命名已一致（`<域>_repository.py`），无需再动 |

## 4. 影响面与验证

- import 更新：`app/routes/__init__.py`（页面/API 两组分区注册）、2 个测试的
  monkeypatch 字符串目标（`app.routes.backtest_training.*` →
  `app.routes.pages.backtest_training.*`，均为 skip 状态的遗留用例）、
  `export_file_service` 3 处 import（export_api / export_service / test_c7_export）。
- 路由表冒烟：应用可启动，143 条规则，页面路径（/login、/admin/*、
  /backtest-training/*、/google-sheet/create、/performance_analysis/* 等）逐一在位。
- 全量回归 `pytest tests/unit tests/integration`：25 个失败经 HEAD 对照
  （stash 工作区改动后复跑）确认全部为分支既有失败（kline/weight-combination
  方向的在途改动），本次重构零新增失败；本次涉及的 auth/permission/static
  pages/export/SSO 用例全绿。
- 后续新增页面/API 时按 §1 规范落位；`AGENTS.md` 双前端小节已同步
  `app/routes/pages` 路径。
