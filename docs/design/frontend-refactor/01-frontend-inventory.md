# 01 — 前端资产全量清点

> 本文所有数字为 2026-09-04 对工作区实测（正则提取 / grep），是方案其余各分册的事实依据。代码变动后执行前应重新核对。

## 1. 总量

| 指标 | 数值 |
|---|---|
| 模板文件 | 49 个（`templates/` 根 5 个 + 13 个子目录） |
| HTML 总量 | 2318 KB / 55,779 行 |
| 内联 `<script>`（无 src） | 1541 KB，占 HTML 体积 ~66% |
| 内联 `<style>` | 148 KB |
| `static/js` 项目自身文件 | `template-auth.js`(29KB)、`trading-date.js`(1.4KB) |
| `static/css` 项目自身文件 | `template-auth.css`(3.1KB) |
| `static/` 第三方库 | ~1608 KB JS（Bootstrap 全变体+layui）+ 全量 Bootstrap CSS 变体 |
| SSE / WebSocket | 无（日志等全部为 HTTP 轮询） |

## 2. 孤儿模板（无任何路由引用，F0 删除）

| 文件 | 行数 | 说明 |
|---|---|---|
| `templates/base.html` | 124 | 旧 C3 布局基座，无任何模板 extends 它 |
| `templates/index.html` | — | 旧首页，引用 CDN，无 render_template |
| `templates/index2.html` | — | 旧版式，引用 CDN，无 render_template |
| `templates/sjhp.html` | — | 内联 style 9.4KB，无 render_template |

验证命令：`grep -rn "sjhp\|index2" app/routes/*.py`（无输出）；`grep -rn "extends \"base.html\"\|extends 'base.html'" templates`（无输出）。

## 3. 页面路由清单（37 条，静态化后 URL 全部保持不变）

| 蓝图 | 路由 | 渲染模板 | 当前服务端上下文 |
|---|---|---|---|
| admin_bp | `/admin/` | admin/dashboard.html | 概览数据（`admin.py:31`） |
| admin_bp | `/admin/tasks` | admin/tasks.html | 4 个枚举列表（`admin.py:41`） |
| admin_bp | `/admin/config` `/navigation` `/logs` `/templates` `/results` `/model-summary` `/eastmoney-kline` `/scheduler` `/users` `/roles` | 对应 admin/*.html | 无 |
| admin_bp | `/admin/google-sheets` | admin/google_sheets.html | `google_sheet_table_type_options` |
| google_sheet_bp | `/google-sheet/` | google_sheet/index.html | `version`（query 透传） |
| google_sheet_bp | `/google-sheet/create` | 按版本分发 c31/c5/c7/c4/C3 | `version` 或 `restart_task_id` 推导 |
| google_sheet_bp | `/google-sheet/merge-export` | google_sheet/merge_export.html | 无 |
| google_sheet_bp | `/google-sheet/detail` | 按版本分发 c5/c7/c4/C3 | `version` 或按 `task_id` 查库推导 |
| backtest_training | `/backtest-training/create` `/list` | 同名页 | 无 |
| backtest_training | `/backtest-training/detail/<task_id>` `/global-preview/<task_id>` | 同名页 | 路径参数 task_id |
| backtest_training | `/backtest-training/result/<int:result_id>` | backtest_training/result.html | **服务端查库**补 task_id |
| backtest_training | `/backtest-training/result/<int:result_id>/export-preview` | result_export_preview.html | result_id |
| backtest_multi_product | 同上形状 5 条页面路由 | backtest_multi_product/* | 同上形状 |
| eastmoney_kline_bp | `/eastmoney-kline` | eastmoney_kline/index.html | 无 |
| global_preview_bp | `/global-preview` `/global-preview/single_product` | global_preview/index.html | 无 |
| auth_pages_bp | `/login` | login.html | `next_url` |
| xpl_bp | `/xpl/` `/xpl/v1` `/xpl/v2` | xpl/*.html | 无 |
| yule_bp | `/yule/` `/yule/sjxz` | yule/index.html / sjxz.html | 无 |

> 注意两个"按 query 参数返回不同文档"的页面组（`/google-sheet/`、`/create`、`/detail`），是静态部署下唯一需要特殊处理的点，方案见 `05` §2.3/§3.2。

## 4. 模板清单（45 个在用，按内联 JS 降序，节选）

| 模板 | 行数 | 内联 JS | 内联 CSS | 继承自 |
|---|---|---|---|---|
| google_sheet_c7/create.html | 2801 | 84.2KB | — | google_sheet/base |
| google_sheet_c7/detail.html | 2636 | 83.2KB | — | google_sheet/base |
| xpl/v2.html | 2724 | 78.5KB | — | admin/base |
| google_sheet_c5/detail.html | 2497 | 77.5KB | — | google_sheet/base |
| google_sheet_c4/detail.html | 2510 | 77.3KB | — | google_sheet/base |
| google_sheet_c31/create.html | 2506 | 76.4KB | — | google_sheet/base |
| google_sheet_c5/create.html | 2567 | 74.0KB | — | google_sheet/base |
| google_sheet_c4/create.html | 2335 | 71.1KB | — | google_sheet/base |
| backtest_multi_product/result.html | 2162 | 61.4KB | — | admin/base |
| backtest_training/result.html | 2086 | 59.3KB | — | admin/base |
| google_sheet/detail.html | 1967 | 58.7KB | — | google_sheet/base |
| xpl/v1.html | 2109 | 58.5KB | — | admin/base |
| google_sheet/create.html | 1835 | 57.1KB | — | google_sheet/base |
| yule/sjxz.html | 2101 | 46.8KB | 20.5KB | 无（独立页） |
| admin/tasks.html | 1366 | 38.7KB | — | admin/base |
| eastmoney_kline/index.html | 1466 | 34.6KB | 6.9KB | 无（独立页） |
| 其余 29 页 | ≤1188 | ≤47KB | ≤9.4KB | 见继承列 |

继承分布（45 = 39 继承页 + 2 基座 + 4 独立页）：**28 页 extends `admin/base.html`，11 页 extends `google_sheet/base.html`，4 页独立完整 HTML**（login、yule/index、yule/sjxz、eastmoney_kline/index）；2 个基座文件在所属族全部改造完成后删除。

## 5. Jinja 注入点全量清单（静态化必须逐条消掉的仅有这些）

### 5.1 数据注入（`{{ }}`，15 类）

| 注入 | 出现处 | 用途 |
|---|---|---|
| `{{ task_id }}`（非 tojson）×10 | backtest 双胞胎的 detail/global_preview/result 页 href 与展示 | 拼详情链接、页面展示 |
| `{{ task_id\|tojson }}` ×6 | backtest 双胞胎 detail/global_preview | JS 常量 `const TASK_ID = ...` |
| `{{ result_id\|tojson }}` ×4 + `{{ result_id }}` ×1 | backtest 双胞胎 result、export_preview | JS 常量、返回链接 |
| `{{ version }}` ×4 | google_sheet_c5/c7/detail.html **JS 模板字符串内**（高危，见 `03` §5） | restart/detail 跳转 URL |
| `{{ next_url }}` ×1 | login.html:219 隐藏域 | 登录后回跳 |
| `{{ 'true' if auth_enabled else 'false' }}` ×4 | 两个 base + login + yule/sjxz | 客户端鉴权开关（决策 D3：直接删除） |
| `{{ url_for(...) }}` ~40 处 | 全部页面 | 静态资源路径 + 页内链接（字面量替换） |
| `{{ google_sheet_table_type_options \| tojson }}` ×1 | admin/google_sheets.html:130 | JS 常量 |
| `{{ option.value }}` `{{ option.label }}` 等 option 循环 ×6 | admin/google_sheets.html ×2、admin/tasks.html ×4 | `<option>` 渲染 |

### 5.2 语句（`{% %}`）

| 语句 | 数量 | 说明 |
|---|---|---|
| `{% extends %}` | 39 | 布局继承（D6 内联展开） |
| `{% block %}/{% endblock %}` | ~146 | 同上 |
| `{% if %}/{% elif %}/{% else %}/{% endif %}` | 16 | version 分支（google_sheet/base 导航高亮）+ template_id 分支 |
| `{% for option in ... %}` | 8 | 上表 option 循环 |
| `{% set %}` | 2 | google_sheet/base 内 version/permission 推导 |

### 5.3 服务端页面逻辑（不是语法但随静态化消失，必须前端化）

| 逻辑 | 位置 | 前端化方案 |
|---|---|---|
| `_resolve_task_version()` 按 task_id/restart_task_id 查库决定渲染哪个版本的模板 | `app/routes/google_sheet.py` | dispatcher 页：fetch `/api/tasks/<id>` 取 task_type → `location.replace` 补 `version=` 参数 |
| result 页由 result_id 查库补 task_id | `app/routes/backtest_training.py:46`、backtest_multi_product 同 | 页面初始化时已 fetch 结果数据，把 task_id 从响应中取（`03` §4.3） |
| admin/tasks、google_sheets 枚举注入 | `app/routes/admin.py:41,87` | `/api/meta/enums` 已返回全部所需枚举（`meta_api.py:28`） |

## 6. CDN 外链依赖（11 个页面，9 种库）

| 库 | 引用页面 | 备注 |
|---|---|---|
| chart.js（两个版本 ×5 页） | admin/dashboard、backtest 双胞胎 result、chart 用户 | 双版本并存 |
| xlsx-js-style 1.2.0 ×2 | backtest 双胞胎 result（导出） | |
| jquery（两个 CDN ×2） | xpl 页 | 同库不同源，版本不同 |
| gsap + ScrollTrigger | yule/sjxz | 动效 |
| **tailwindcss CDN（JIT 运行时）** | yule/sjxz | 生产不推荐，运行时编译 CSS |
| swiper 11 | yule/sjxz | |
| bootstrap@5.1.3 CDN | templates/base.html（孤儿）、google_sheet/index.html | 后者在用！ |
| layui（已本地 static） | eastmoney_kline | 已本地化样板 |

> CDN 本地化列为可选批次（`05` §6）：内网/离线 nginx 部署时必须做；本次静态化不强制。

## 7. 浏览器存储键清单（搬移时不可破坏的契约）

| 键 | 使用者 | 内容 |
|---|---|---|
| `access_token` / `refresh_token` | template-auth.js | JWT（拦截 fetch 自动附加/刷新） |
| `templateTheme` | template-auth.js | 主题切换 |
| `google_sheet_form_data` / `google_sheet_c4/c5/c7_form_data` | 对应 create 页 | 表单恢复 |
| `tasksPerPage` | 任务列表页 | 分页偏好 |
| `sidebarCollapseState` | admin/base.html 内联脚本 | 侧栏折叠状态 |
| `foodSelectionHistory` / `customFoodDatabase` | yule/sjxz | 页面业务数据 |

## 8. 共享运行时现状（静态化后进入 `static/js/common/`）

1. **`template-auth.js`（29KB）**：全局 fetch 包装（自动附带 Bearer、401 刷新重放、按 `authExemptPaths` 豁免）；localStorage token 管理；基于 `data-permission` 的导航过滤；`template-auth-ready` 事件；body `template-auth-pending → ready/login` 状态机与加载遮罩。**它已经是事实上的前端运行时内核**，本次唯一改动是删除 `isAuthEnabled()` 对 `data-auth-enabled` 的读取（属性缺失时本就默认 true，见 `03` §6）。
2. **`trading-date.js`（1.4KB）**：交易日日期工具，3 个页面引用。
3. **admin/base.html 内联脚本（~70 行）**：侧栏折叠状态持久化，随基座内联展开到各 admin 页（或收敛为 common 脚本，见 `02` §2）。
4. **google_sheet/base.html 内联脚本（~28 行）**：`sanitizeJSONString` / `parseJsonArray` / `extractSpreadsheetId` 工具，**已被 ≥6 个页面复制粘贴**（重复度实测见 §9），静态化时收敛进 `common/utils.js`。

## 9. 页面间重复度实测（函数名集合 Jaccard 相似度）

| 页面对 | 函数数 | 交集 | 相似度 |
|---|---|---|---|
| c5/create vs c7/create | 207 / 226 | 206 | **91%** |
| c4/create vs c5/create | 183 / 207 | 158 | 68% |
| backtest list vs multi list | 103 / 100 | 97 | **92%** |
| backtest result vs multi result | 192 / 190 | 183 | **92%** |
| backtest detail vs multi detail | 171 / 180 | 163 | 87% |
| backtest create vs multi create | 196 / 123 | 38 | 14%（确实不同） |

> 本方案**不做**去重合并（非目标）；数据仅用于说明现状技术债与未来治理方向。

## 10. 已有的正面样板

`static/eastmoney-kline/js/` 已是抽离形态：`utils.js`、`http/eastMoneyKlineApi.js`（API 层独立文件）、`excelExport.js`，页面通过普通 `<script src>` 按序引入。证明"无构建、普通 script、目录分层"的模式在本仓库可行，`02` 的规范即以此为准绳。
