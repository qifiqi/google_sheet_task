# 01 — API 端点清点与职能位置审计

> 统计口径：101 个 API 端点（JSON 接口）+ 37 个页面路由，逐文件清点自 `@*.route` 装饰器（2026-09-04）。

## 1. 现状总表（按蓝图）

| 蓝图 | url_prefix | API 端点 | 页面路由 | 职能判定 |
|---|---|---|---|---|
| task_api_bp | `/api` | 12 | 0 | ✅ 任务域 API |
| auth_api_bp | `/api` | 14 | 0 | ⚠️ auth + 用户/角色/权限 CRUD（`/api/admin/users|roles|permissions`）|
| config_api_bp | `/api` | 11 | 0 | ⚠️ 一个文件 4 个资源域（config / system-configs / navigation-menu-items / logs）|
| scheduler_api_bp | **无** | 9 | 0 | ⚠️ 注册时不带 `url_prefix`，路由内手写全路径 `/api/admin/scheduler/...` |
| export_api_bp | `/api/exports` | 10 | 0 | ✅ 导出域 |
| google_sheet_api_bp | `/api` | 7 | 0 | ✅ Sheet 注册表/Token 池 |
| admin_bp | `/admin` | **7** | 13 | ❌ 页面蓝图寄宿 API（`/admin/api/*`）|
| backtest_training_bp | `/backtest-training` | **6** | 6 | ❌ 同上（`/backtest-training/api/*`）|
| backtest_multi_product_bp | `/backtest-multi-product` | **6** | 5 | ❌ 同上 |
| global_preview_bp | `/global-preview` | **2** | 2 | ❌ 同上 |
| xpl_bp | `/xpl` | **2** | 3 | ❌ 同上 + 无鉴权 + 非信封 |
| result_api_bp | `/api` | 3 | 0 | ✅ 结果域（B1.1 新归位）|
| meta_api_bp / stock_api_bp / database_api_bp | `/api` | 3/1/3 | 0 | ✅ |
| 页面蓝图（google_sheet / eastmoney_kline / auth_pages / yule） | — | 0 | 12 | ✅ |

## 2. 响应信封合规

总体合规：绝大多数路由文件经 B1 批次改造后统一走 `success()/error()`（`app/utils/api_response.py`）。

| 文件 | 现状 | 判定 |
|---|---|---|
| `xpl.py` | `jsonify` ×11、`status/message` 手写结构、无一处 success/error | ❌ 全文件游离于信封体系（错位整改时一并迁移） |
| `admin.py:146` | `dashboard_overview` 用 jsonify 透传 `runtime_view_service` 返回 | ⚠️ 已在 docstring 声明"B3 迁移时收敛信封"，登记为待办 |
| google_sheet / bt / bmp / global_preview / yule / export_api | 各残留 1 处 jsonify | ⚠️ 逐一核对：文件下载/重定向类可豁免，JSON 类应收敛 |
| `errors.py:27` | `_wants_json()` 以 `"/api/" in path + Accept` 判定，已兜住非 `/api` 前缀端点的错误信封 | ✅ 兜底有效；但该启发式正是"API 寄宿页面蓝图"逼出来的补丁——归位后可简化为 `startswith("/api")` |

## 3. 鉴权覆盖

| 范围 | 现状 | 判定 |
|---|---|---|
| 各 API 蓝图 | `login_required` 数与端点数吻合（task 12/13、config 12/11、scheduler 10/9、export 11/10…）| ✅（个别 helper 复用装饰器导致计数 ±1，抽查无裸奔）|
| `xpl.py` | `login_required` ×0；`/analyze`、`/v1/analyze` 为 POST 计算 API | ❌ **匿名可调用**，且 analyze 为纯计算接口（无副作用）风险有限，但对外部署即暴露算力；补 `@login_required` 一行即可 |
| 页面路由（admin 13 页、bt/bmp/gs 等） | 均无服务端守卫 | ✅ 符合既定设计：页面 HTML 公开，由 `template-auth.js` 客户端鉴权 + 数据 API 服务端鉴权 |
| 权限粒度 | 仅页面级 `page:*` 权限（`config.py:453` 注释确认接口级细粒度权限已移除）| ✅ 既定决策 |

## 4. `/api` 命名空间形态盘点（碎片化证据）

同一"后台管理 API"语义存在三种 URL 风格、三个文件：

| 风格 | 端点 | 文件 |
|---|---|---|
| `/admin/api/*` | scheduler/status、dashboard/overview、model-summary×3、tasks/runtime-detail、scheduler/cleanup | admin.py |
| `/api/admin/users\|roles\|permissions` | 用户/角色/权限 CRUD ×7 | auth_api.py |
| `/api/admin/scheduler/*` | 调度任务 CRUD ×9 | scheduler_api.py |

前端调用的 API 前缀共 5 种形态：`/api/*`、`/api/admin/*`、`/admin/api/*`、`/backtest-training|backtest-multi-product/api/*`、`/global-preview/api/*`。

## 5. 职能位置问题清单（P3 结构批，URL 保持不变仅挪代码）

| # | 问题 | 证据 | 建议归属 |
|---|---|---|---|
| 5.1 | admin.py 227 行中 130 行是 API；7 个 `/admin/api/*` 端点寄宿页面蓝图 | `admin.py:97-227` | dashboard/overview+model-summary → 新 `dashboard_api.py` 或并入 result_api；scheduler 两个 → scheduler_api.py；runtime-detail → task_api.py |
| 5.2 | bt/bmp 各 6 个 API 与页面混居，且两文件 API 近乎同构（import-excel / task-results / task-result / export-preview / task-summary / global-preview） | bt:79-279、bmp:207-349 | 抽 `backtest_api.py`（以 task_type 参数区分），与 export_api 的 `/exports/backtest-*` 职责划清：取数归 backtest_api，文件流归 export_api |
| 5.3 | global_preview 2 个 API 混居 | `global_preview.py:67,90` | 并入 backtest_api 或独立 preview_api |
| 5.4 | config_api 一个文件 4 个资源域；日志 API（`/api/logs`、`/api/logs/latest`）挂在 config 名下 | `config_api.py` 全文 | 拆 logs_api.py、navigation_api.py；config 域保留 |
| 5.5 | scheduler_api_bp 注册无 `url_prefix`，路径手写在装饰器里；与 task_api 等风格不一致 | `app/routes/__init__.py:44`、`scheduler_api.py:41` | 统一为 `url_prefix='/api'` + 短路径 |
| 5.6 | 用户/角色 CRUD 在 auth_api（管理域）而 admin 页面蓝图叫 admin——"admin API"分裂在 2 个文件 | `auth_api.py:156-306` | 接受现状（auth 域聚合）或迁 admin 域，二选一并写进蓝图 README；倾向前者，仅统一 URL 注释 |
| 5.7 | task_api.py 567 行：`/tasks/<id>/results`（208-443，235 行）实为结果域读取+CSV 导出 | `task_api.py` | 结果读取并入 result_api；CSV 流保留 export 域 |
| 5.8 | xpl.py `analyze_data` ~90 行计算逻辑内联路由层 | `xpl.py:40-130` | 抽 `xpl_analysis_service.py`；路由只做 HTTP 编排 |

## 6. 整改约束

- **URL 一律不变**：前端 97 处 fetch 调用点、`template-auth.js` 的豁免清单与 legacyPathMap 均按现 URL 写死，归位只动蓝图归属与注册；
- `errors.py` 的 `_wants_json()` 在 `/admin/api/*` 等寄宿端点归位后可简化，但 Accept 启发式建议保留（fetch 默认 Accept 为 `*/*`）；
- 归位以文件为单位提交，每文件一次 commit，配合 `tests/integration`（test_unified_envelope、test_page_permission_sync 等）回归。
