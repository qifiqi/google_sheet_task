# Vue 前端修复方案（2026-09）

对照纯静态版（`templates/` + `static/js/pages/`）审计 `frontend/` Vue 3 SPA 后确认的三类问题与分阶段修复方案。审计范围：接口契约、明暗主题、页面覆盖度。

## 问题清单

### P1 接口契约错位（系统性，页面数据为空）

后端统一信封 `{"status","code","message","data"}`（`app/utils/api_response.py`），HTTP 层错误一律非 2xx（`app/errors.py`）。`frontend/src/api/index.js` 拦截器 `res => res.data` 只解到信封层，而视图代码按**2026-09 数据层重构前的旧契约**取值（`res.tasks` / `res.pagination` / `res.results`），两层错误叠加：

| 视图 | 现读取 | 后端实际 data 形状 |
| --- | --- | --- |
| `task/TaskListInner.vue:248`、`admin/Tasks.vue:187`、`backtest/List.vue:101`、`backtest-multi/List.vue:101` | `res.tasks`、`res.pagination?.total` | `{items,total,pages,current_page,per_page,statistics}` |
| `task/Detail.vue:322,332,344,431` | `res.task`（√键名但层级错）、`res.result_summary`（已不存在）、`res.logs`、`res.results`、`res.status` | `{task}` / `{logs}` / `{items,...}` / `{db_status,...}` |
| `admin/GoogleSheets.vue:141`、`task/CreateC3.vue:241`、`CreateC5.vue:448`、`CreateC31.vue:303` | `res.items`（层级错） | `{items}` |
| `admin/Dashboard.vue:156-160` | `data.summary`（层级错） | `{summary,active_tasks,recent_tasks,checked_at}` |
| `backtest/Detail.vue:486`、`backtest-multi/Detail.vue:220` | `res.total \|\| res.pagination?.total` | `{items,total,...}` |
| `composables/useAuth.js`、`admin/Navigation.vue:167` | `res.data.*`（恰好取对信封层） | 随新解包层级需同步调整 |

正确取值仅 `useAuth`/`Navigation` 两处，属侥幸对齐信封层。

**URL 错误**：股票搜索后端唯一入口 `/api/search-stocks`（`app/routes/stock_api.py`），Vue `api/backtest.js:5`、`api/backtestMulti.js:6` 调 `/backtest-training|/backtest-multi-product + /api/search-stocks` → 404。

**缺失封装**：`/admin/api/model-summary` 三件套、`/backtest-*/api/task-result/<id>/export-preview`、`/google-sheet-tokens/reconcile`、`/performance_analysis/analyze`（v2 主端点）、`/global-preview/api/*`。

### P2 明暗主题破碎

1. `views/task/List.vue` 写死 `:theme="darkTheme"` 与 `background:#0a0e1a` —— 该页永远暗色，与全局开关脱节。
2. `styles/naive-theme.js` 只有一份硬编码暗色 overrides，且仅 task/List 局部挂 `NConfigProvider`；`Login.vue`、`performance_analysis/*.vue` 用 naive 组件无 provider → 暗色模式下永远亮色皮肤。
3. 双 UI 库（Element Plus 31 文件 / naive-ui 5 文件）各管各的：`styles/index.scss` 只映射了 `--el-*`，naive 完全没接。
4. 硬编码亮色残留：`index.scss` 的 `.mono-pre`/`.tag-wall`/`.info-banner`/`.admin-tasks-page__config-pre`/`.admin-tasks-page__muted`；`TaskListInner.vue:317,401` 的 `#111827`；Dashboard 统计卡渐变。
5. `index.html` 无主题引导脚本 → 暗色用户首屏闪白；`useTheme.js` 启动即固化系统偏好到 localStorage，此后不跟随系统。

### P3 与静态版的内容差距

整页缺失（后端与静态页均在，Vue 无实现，且部分已造成侧边栏死链）：

| 功能 | 静态来源 | 后端 | 导航路径 | Vue 现状 |
| --- | --- | --- | --- | --- |
| 东方财富 K 线 | `static/js/pages/eastmoney_kline_index.js`（949 行） | `/admin/eastmoney-kline` 页 + eastmoney API | `/admin/eastmoney-kline` | 无 → 死链 |
| 单品全局预览中心 | `global_preview_index.js`（154 行） | `/global-preview/api/*` | `/global-preview/single_product` | 无 → 死链 |
| 单模型汇总 | `admin_model_summary.js`（545 行） | `/admin/api/model-summary` 三件套 | `/admin/model-summary` | 路由错指 `Results.vue` |
| Google Sheet C7 创建/详情 | `google_sheet_c7_create.js`、`google_sheet_c7_detail.js`（1547 行） | C 系任务 | `/google-sheet/?version=c7` | 无 c7 → 死链 |
| 合并导出 | `google_sheet_merge_export.js` | `/api/exports/*` | — | 无 |
| 绩效分析 v2 | `performance_analysis_v2.js` | `/performance_analysis/v1/analyze`、`/analyze` | `/performance_analysis/v2` | 只有 v1 → 死链 |

缩水：C 系详情静态版 C3/C5/C7 各约 1400–1550 行（版本专属回填/结果渲染），Vue 统一 `task/Detail.vue` 658 行且无 version 分支。导航适配 `useNavigation.js` 的 LEGACY_PATH_MAP 缺 c7/eastmoney/global_preview/v2 映射。

## 修复方案

原则：延续 AGENTS.md——迁移是翻译不是重设计；前端不新增鉴权逻辑；全库单一响应契约不动后端。

### Phase 1 接口契约统一

1. `api/index.js` 拦截器**深解包**：成功返回 `res.data.data`（信封 data 载荷），业务错误（非 2xx）统一抛带 `message`（信封 message 优先）的 Error；`responseType === 'blob'` 特判直接返回 Blob。401 refresh 流程保持现状（裸 axios 不受影响）。
2. 视图批量修正旧契约键名：`res.tasks → res.items`、`res.pagination?.total → res.total`、`res.results → res.items`、`res.result_summary` 移除（改由 results 端点派生）、`checkTaskStatus` 读 `db_status`；`useAuth`/`Navigation.vue` 去掉多取的一层。
3. URL 修正：两处 search-stocks 改 `/api/search-stocks`。
4. 补 API 封装：`api/admin.js` 增 model-summary 三件套；`api/backtest.js` 增 export-preview；`api/googleSheet.js` 增 reconcile；`api/performance_analysis.js` 增主分析端点；新增 `api/globalPreview.js`（预览中心）。
5. 验收：`npm run build` 通过；grep 无 `res.pagination`/`res.tasks` 残留。

### Phase 2 主题收敛

1. `styles/naive-theme.js` 重构为 `buildNaiveThemeOverrides(isDark)`，输出明/暗两份 overrides（品牌色一致，表面色随主题）。
2. `AppLayout.vue` 全局挂 `NConfigProvider + NMessageProvider + NDialogProvider`（`useTheme().isDark` 切 `darkTheme/null`）；`Login.vue` 自挂。`task/List.vue` 移除局部 provider 与硬编码底色。
3. 硬编码色清理：`TaskListInner` 改用 `--app-*` CSS 变量；`index.scss` 四处亮色残留补 `[data-theme='dark']` 变体。
4. `index.html` 加内联主题引导脚本（读 localStorage 设 `data-theme` + `.dark`，防闪白）；`useTheme` 未显式选择时跟随系统变化。
5. 验收：build 通过；明暗切换下 naive/Element 组件与页面底色一致。

### Phase 3 页面补齐

- 3a（结构）：路由补 `/task/create/c7`、`/admin/eastmoney-kline`、`/global-preview/single_product`、`/performance_analysis/v2`、`/admin/model-summary`（指真页面）；LEGACY_PATH_MAP 补 c7；`TaskListInner` 版本映射补 c7；Phase 1 的 API 封装落地。
- 3b（小页）：全局预览中心（154 行）、单模型汇总（545 行）直接翻译。
- 3c（大页）：东方财富 K 线（949 行）、绩效分析 v2（约 800 行）、C7 创建（约千行）、C 系详情版本分支——按静态页逐页翻译，工作量最大，允许分批交付。
- 验收：侧边栏无死链；每页翻译对照静态页字段清单（表单初始化/localStorage 恢复/回填/提交 payload 四处同步）。

## 执行记录

- [x] Phase 1：拦截器深解包（`api/index.js`：返回 data 载荷、blob 特判、错误统一带信封 message）；视图修正 19 处（4 个任务列表、3 个详情页、预览页 ×2、Results/Navigation/Users/Roles/GoogleSheets/Scheduler、useAuth/useNavigation、importToken 提示 ×4）；search-stocks 两条 URL 改 `/api/search-stocks`；补封装 model-summary 三件套 / export-preview / reconcile / 主分析端点 / 新建 api/globalPreview.js
- [x] Phase 2：naive-theme.js 重构为 `buildNaiveThemeOverrides(isDark)` 明暗两份；AppLayout 全局挂 NConfigProvider + Message/Dialog Provider；task/List 移除局部 darkTheme 与写死底色；TaskListInner 硬编码色改 CSS 变量；index.scss 追加暗色组件变体（mono-pre/tag-wall/info-banner/config-pre 等）；index.html 加主题引导脚本防闪白；useTheme 未显式选择时跟随系统
- [x] Phase 3a：路由补 `/task/create/c7`、`/admin/eastmoney-kline`、`/global-preview/single_product`、`/performance_analysis/v2`；model-summary 改指真页面；LEGACY_PATH_MAP 与 TaskListInner 版本映射补 c7
- [x] Phase 3b：全局预览中心（`views/global_preview/SingleProduct.vue`）、单模型汇总（`views/admin/ModelSummary.vue`，含概览卡/筛选/动态指标列/重建轮询/CSV 导出弹窗）
- [x] Phase 3c（部分）：东方财富 K 线（`views/admin/EastmoneyKline.vue` + `api/eastmoney.js` + `composables/useXlsxJsStyle.js`）、绩效分析 v2（`views/performance_analysis/V2.vue`）、C7 创建（`views/task/CreateC7.vue`），均由静态页逐字段翻译，Element Plus + CSS 变量实现
- [ ] Phase 3c（遗留）：C 系任务详情的版本分支回填（静态 c3/c5/c7 detail 各约 1400–1550 行，现统一 Detail.vue 658 行无版本分支）；google_sheet 合并导出页
- [x] `npm run build` 通过（新增页面均已进产物 chunk）

### 已知遗留与说明

1. 任务详情页版本分支（C3/C5/C7 各自的指标渲染、回填差异）未翻译，当前为通用实现。
2. K 线页行情数据走 JSONP 直连 push2his.eastmoney.com（静态版同款）；后端未来提供同源代理时可整体替换 `api/eastmoney.js`。
3. 绩效分析 v2 的 Word 报告文件名固定为兜底名（blob 拦截器契约拿不到 Content-Disposition），如需还原需给 api 层加"返回完整 response"的 raw 变体。
4. naive 图表/表格在主题切换后，已渲染的 Chart.js 轴色需重新分析才刷新（沿用静态版行为）。
