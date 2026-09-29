# 老模板（静态版）移动端适配审查报告

- 日期：2026-09-29
- 范围：`templates/` + `static/` 静态版全部 43 个页面（Vue SPA `frontend/` 不在本次范围）
- 触发：手机上侧边栏打不开、显示异常；要求覆盖卡片、C 系列、回测各内容的手机适配
- 性质：纯审查（未改代码），修复方案见 §6

## 1. 背景速览

静态版导航分两族（`static/js/common/components/navbar.js` 按 pathname 前缀选择）：

| 导航族 | 外壳形态 | 页面数 | 手机端现状 |
| --- | --- | --- | --- |
| admin 族（`/admin/*`、`/backtest-training/*`、`/backtest-multi-product/*`、`/performance_analysis/*`、`/global-preview`） | 左侧固定侧边栏 | 28 | **完全无导航（P0）** |
| google_sheet 族（`/google-sheet/*`，含 c31、c4、c5、c7 版本分支） | 顶部 navbar（`navbar-expand-lg`） | 9 | 顶栏可折叠展开，功能可用 |
| 独立页（`/login`、`/eastmoney-kline`、`/google-sheet/merge-export`） | 各自独立 | 3+ | 基本可用 |

全部模板均有 viewport meta（无一遗漏）。

## 2. 结论摘要

| 级别 | 问题 | 影响 |
| --- | --- | --- |
| **P0** | admin 族侧边栏手机端 `display:none` 且全站无任何打开入口 | 28 个页面在手机上零导航：无法跳转、无法退出登录（退出按钮在侧栏 dropup 里）、无法切主题 |
| P1 | 卡片头部 `d-flex justify-content-between` 不换行（12 个文件约 23 处） | 详情页头部按钮组（停止/重启/检查状态/返回）在 375px 宽溢出/挤压标题 |
| P1 | C 系列详情页信息卡 `col-4/col-8` 键值行（4 页 × 9 行） | 长任务名/任务 UUID 在手机 2/3 宽度内溢出卡片，无 `overflow-wrap` |
| P2 | 大数据表横滚方案：1680px/1580px/920px min-width | 有滚动容器不破版，但手机横滚体验差，无首列冻结（除 model_summary） |
| P2 | 回测结果页 8 张 KPI 卡 `col-md-3` | 手机单列堆叠约 8 屏；dashboard 卡片已有更好的 `col-6` 先例 |
| P2 | 顶栏不吸顶 | C 系列长表单滚到底部后无法回到导航 |
| P2 | 16 个页面 CSS 零媒体查询 | 适配靠 Bootstrap 栅格兜底，断点行为不一致 |
| P3 | 权重组合分析固定列宽、v2 工具栏、admin logs 按钮行等局部问题 | 局部挤压/换行不佳 |

## 3. P0：admin 族手机端侧边栏不可达（根因）

### 3.1 证据链

1. 28 个模板外壳一致（如 `templates/backtest_training/list.html:26`）：

   ```html
   <nav class="col-md-3 col-lg-2 d-md-block sidebar collapse" data-navbar></nav>
   ```

2. `navbar.js:133` 渲染时原样保留该 class：`classes: 'col-md-3 col-lg-2 d-md-block sidebar collapse'`，菜单内容由 `adminSidebar()` 注入。
3. Bootstrap 语义：`.collapse` = `display:none`，除非带 `.show`；`d-md-block` 只在 ≥768px 用 `!important` 恢复显示。**<768px 时侧边栏是 `display:none`**。
4. 全库检索（`static/js`、`static/css`、`templates/`）：不存在任何指向该 nav 的 `navbar-toggler`、offcanvas 按钮或其他 `.show` 注入逻辑。`adminSidebar()`（navbar.js:91-125）输出里没有 toggler；页面头部只有业务按钮。
5. `admin-shell.js` 只负责侧栏内部子菜单（`#templateSidebarMenu` 里的二级 `.collapse`）的状态记忆，不涉及外壳显隐。

结论：手机端这 28 个页面没有任何导航入口。受影响页面清单见附录 A。

### 3.2 为什么"直接去掉 collapse"也不行

`static/css/components/sidebar.css` 只有两条 `min-width` 媒体查询（:193、:208），**没有任何 <768px 规则**。`.sidebar` 基础样式（:3-12）是 `min-height: 100vh; flex: 0 0 auto`——若手机端强行显示，会以静态块形态占满首屏，把正文推到第二屏。即外壳在移动端既"打不开"，也"没设计过打开后的样子"。

### 3.3 修复方案（二选一，均只需改 navbar.js + sidebar.css，28 页自动全覆盖）

- **方案 A（推荐）：移动端顶栏 + Offcanvas 侧滑**
  - `adminSidebar()` 输出前插入移动端顶栏（`d-md-none sticky-top`）：品牌 + 汉堡按钮 + 用户下拉；汉堡按钮控制侧栏容器。
  - 侧栏容器在 <768px 走 Bootstrap Offcanvas（左滑出，自带遮罩与滚动锁定）；≥768px 用几行 CSS 把 offcanvas 覆写回静态固定侧栏（保留现有桌面观感）。
  - 优点：手机体验最佳；改动集中在 navbar.js（菜单本就统一渲染）与 sidebar.css。
- **方案 B（最小改动）：移动端顶栏 + collapse 展开**
  - 顶栏汉堡按钮 `data-bs-toggle="collapse"` 直接指向侧栏 nav（给它补 id），点击后加 `.show` 显示；sidebar.css 补 <768px 规则（`min-height:auto; max-height:70vh; overflow-y:auto; width:100%`），展开为顶部可滚动块。
  - 优点：改动最小、机制与现状同源；缺点：展开时正文被推下去，体验一般。

注意：navbar.js 头部注释的"渲染产物与原基座逐字节等价"红线约束的是静态化迁移期；本修复是行为升级，落地时需在该文档与 navbar.js 注释中登记修订（沿用 D6 修订先例）。

## 4. P1 问题

### 4.1 卡片头部按钮组不换行

模式：`card-header d-flex justify-content-between align-items-center`（无 `flex-wrap`），右侧按钮组在手机溢出。分布（`grep -c`）：

- C 系列详情：`google_sheet/detail.html`×3、`google_sheet_c4|c5|c7/detail.html` 各×3（典型：`google_sheet/detail.html:29` 头部 + :31-60 四按钮 btn-group）
- C 系列创建：`create.html`×1、c4/c5/c7/c31 create 各×2
- admin：`config.html`×1、`dashboard.html`×1、`google_sheet/index.html`×1

对照：回测域新页面（`backtest_training/detail.html` 等）已用 `... flex-wrap gap-3` 的正确写法。

修复：统一追加 `flex-wrap gap-2`（约 23 处纯 class 追加，低风险）；按钮组加 `mt-2 mt-md-0` 类间距更稳。

### 4.2 C 系列详情页信息卡 col-4/col-8 溢出

`google_sheet/detail.html:68-83`（c4/c5/c7 同构，各 9 行）：`col-4` 标签 + `col-8` 值。任务名称、任务 UUID 等长值在手机 2/3 宽度内无换行手段（CSS 无 `overflow-wrap`），溢出卡片或撑破布局。

修复（任选，建议叠加）：
1. 值单元格加 `overflow-wrap: anywhere; min-width: 0;`（一行 CSS，`.card-body .col-8` 作用域）；
2. 手机端改为上下堆叠：`col-12 col-md-4` / `col-12 col-md-8`（9 行 × 4 页同步改）。

## 5. P2 问题

### 5.1 大数据表横向滚动

| 表 | min-width | 容器 | 位置 |
| --- | --- | --- | --- |
| 回测详情汇总表 | 1680px | `.summary-table-wrap` overflow:auto | `backtest_training_detail.css:87`、`backtest_multi_product_detail.css:87` |
| 参数明细表 | 720px | 同上容器 + sticky 表头 | `backtest_multi_product_detail.css:226` |
| 模型汇总表 | 1580px | scroll wrap + sticky 首列 | `admin/model_summary.html:532`（内联样式块） |
| 全局预览表 | 920px | `.preview-table-wrap` | `global_preview_index.css:4` |
| 回测列表 9 列表 | 无 min-width | `table-responsive` | `backtest_training/list.html:103` |

容器都在，不破版；model_summary 已有 sticky-col 先例。可选增强：手机端给首列（任务名/参数列）加 sticky-left；或对汇总表提供"手机精简列"渲染。属体验优化，不阻塞。

### 5.2 回测结果页 KPI 卡手机堆叠过长

`backtest_training/result.html:57-120` 与 `backtest_multi_product/result.html` 同构：8 张指标卡 `col-md-3`，手机全宽单列约 8 屏。对照 `admin/dashboard.html:38-43` 用 `col-xl-2 col-md-4 col-6`（手机两列）。

修复：改为 `col-6 col-md-3`（8 卡变手机 4 行 2 列），卡片内 `metric-value` 字号已有 rem 控制，风险低。

### 5.3 顶栏不吸顶

google_sheet 族 navbar 渲染在 `<div data-navbar>`（如 `google_sheet/create.html:23`），无 `sticky-top`；长表单滚到底部后回不到导航/模式切换。修复：google-sheet 族 classes 加 `sticky-top`；admin 族若按 §3.3 方案 A 做移动顶栏，顶栏自带 sticky（桌面侧栏已 fixed 不受影响）。

### 5.4 页面 CSS 断点覆盖不均

有 @media 的页面 CSS 11 个，零断点的 16 个：`admin_roles/logs/eastmoney_kline/admin_templates`、`backtest_multi_product_list/detail/result`、`backtest_training_global_preview/list/detail/result`、`global_preview_index`、`google_sheet_merge_export/detail`、`performance_analysis_v2`、`weight_combination`。其中多数靠 Bootstrap 栅格已够用（本报告只在有实际破版处立项），但后续改动应优先在有断点体系内做，避免每页各造一套。

## 6. P3 局部问题

- `weight_combination.css:252-254` 固定列宽（44/96/124px）+ `:172` grid `1fr 1fr` 无断点：手机上选品面板拥挤；建议 <576px 时 grid 单列、列宽放宽。
- `performance_analysis/v2.html:48` 工具栏 `col-lg-*` 元素直接放在 `d-flex flex-wrap` 容器内，窄屏按内容收缩，长 label 可能挤压输入框；建议容器改 `row g-2`。
- `admin/logs.html:32-42` 顶部三个 `btn-group me-2` 窄屏换行参差，建议包一层 `d-flex flex-wrap gap-2`。
- `eastmoney_kline/index.html` 为独立页（不在导航族，navbar.js 会移除其挂载点——该页本身无导航元素，属预期），其 CSS 已带 1100px/760px 断点，是全站适配最好的页面，可作为断点参考。

## 7. 做得好的（审查基线，避免误伤）

- viewport meta 全覆盖；栅格基本位（`col-md-*` 窄屏自动堆叠）。
- 创建页提交区 `d-grid gap-2 d-md-flex`（`google_sheet/create.html:303`）是正确的手机按钮模式。
- 回测域新页面（training/multi 的 list/detail）头部均已 `flex-wrap gap-3`，指标卡 `col-12 col-md-6 col-xl-3`。
- 28 张业务表基本都在 `table-responsive` 或 overflow 容器内；C 系列详情结果表有 `table-responsive`（`google_sheet/detail.html:209,249`）。
- model_summary（筛选项格 + sticky 表）、backtest_training_create（991px 断点）、login（640px 断点）已有针对性适配。
- 明暗主题变量齐全，不构成移动端额外风险。

## 8. 建议落地顺序

1. **P0 侧边栏**（navbar.js + sidebar.css，方案 A offcanvas / 方案 B collapse 二选一）→ 28 页恢复导航与退出登录入口。
2. **P1 头部 flex-wrap**（23 处 class 追加）+ **P1 详情信息卡溢出**（一行 CSS 或 col 类替换）。
3. **P2 KPI 卡 col-6**、**P2 google-sheet 顶栏 sticky-top**。
4. P3/P2 可选增强（首列 sticky、weight_combination 断点等）按需排期。

## 9. 回归验证清单

- 宽度四档：375px（iPhone SE/mini）、414px、768px（iPad 竖屏，恰好是 md 断点临界）、992px。
- 每档验证：侧边栏可达性（方案落地后）、暗色主题、模态框（批量导出 modal-lg）、表格横滚容器、图表 canvas 高度。
- 重点页：backtest_training/{list,detail,result}、backtest_multi_product/{list,detail}、google_sheet/{create,detail}?version=c3/c4/c5/c7、google_sheet_c31/create、performance_analysis/{index,v2,weight_combination}、admin/{dashboard,tasks,results,model_summary}。
- 回归命令：`python -m pytest tests/unit tests/integration`（含 `tests/integration/test_xpl_v2_page.py` 页面结构测试，改 nav class 后先跑它）。

## 附录 A：P0 受影响页面（28）

admin：config、dashboard、eastmoney_kline、google_sheets、logs、model_summary、navigation、results、roles、scheduler、tasks、templates、users（13）
backtest_training：create、detail、global_preview、list、result、result_export_preview（6）
backtest_multi_product：create、detail、global_preview、list、result（5）
performance_analysis：index、v2、weight_combination（3）
global_preview：index（1）
