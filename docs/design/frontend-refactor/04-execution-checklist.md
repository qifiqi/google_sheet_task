# 04 — 执行清单（批次 F0~F6）

> 每批一个 git 分支（`refactor/frontend-F<n>`），批内每页一个 commit（`refactor(frontend): de-jinja <page>`），保证**单页可独立 revert**。全批验收通过后合并 `dev_vue`。

## 0. 总则

**搬移纪律**（对应 AGENTS.md "不要做的事"）：

1. 内联 JS **原样剪切**到 `static/js/pages/<名>.js`，不改逻辑、不改顺序、不"顺手优化"；
2. `<script src>` 用普通脚本（无 defer/async/module），放在原内联位置（`02` §3.2）；common 层引入顺序固定：`template-auth.js` → `navbar.js` → `api.js` → `utils.js` → 页面 JS；
3. 每页改造必须同时覆盖：静态 HTML、抽离 JS、抽离 CSS、页面路由切换、该页 localStorage/回填功能验证；
4. 发现本文档未收录的 Jinja 注入点：**先补 `03` 再动代码**；
5. **两步走（B 修订，`02` §3.6）**：c4/c5/c7、backtest 双胞胎等收敛对象，先完成各页机械搬移（`refactor(frontend): de-jinja <page>`）并过验证四件套，再做批内收敛 pass（`refactor(frontend): dedupe <域>`，提升 `common/business/` 并改写调用点），收敛 commit 独立验证、独立可 revert；
6. 页面 JS 的后端请求一律迁入 `common/api.js`（`02` §3.5）；机械搬移阶段可临时保留原 fetch 写法，收敛 pass 或 F6 前必须收口。

**每页验证四件套**：

| 项 | 方法 |
|---|---|
| 视觉零变化 | 改造前后同 URL 截图对比（浏览器 devtools 截全页，含登录后状态） |
| 功能零变化 | 页面功能清单（见 §F1 附表，按页勾选） |
| 回归 | `python -m pytest tests/unit tests/integration` 全绿 |
| 残留 | `grep -n "{{\|{%" <当批页面文件>` 无输出（`03` §7） |

---

## F0 准备批（0 页改造）

1. **zip 归档原版**（决策 D8；2026-09-07 注：4 孤儿已在工作区删除未提交，必须从 git HEAD 打包才能拿到完整 49 文件原版）：
   ```bash
   # 仓库根目录（Git Bash）
   mkdir -p docs/design/frontend-refactor/archive
   git archive --format=zip -o docs/design/frontend-refactor/archive/templates-jinja-source.zip HEAD templates
   unzip -l docs/design/frontend-refactor/archive/templates-jinja-source.zip | grep -c "\.html"   # 期望 49
   ```
   归档核对齐全后，**归档文件不参与任何运行时**。
2. **删孤儿模板**（工作区已删，本步复核 grep 后随 F0 一起提交）：`templates/{base,index,index2,sjhp}.html`。
   ```bash
   grep -rn "render_template" app --include="*.py" | grep -E "sjhp|index2|'base.html'|\"base.html\"|templates/index"   # 期望无输出
   ```
3. **vendor 清理**（逐项 grep 零引用后删，候选清单）：
   ```bash
   # 对每个候选逐项核对（模板与页面内无引用才可删；.map 引用仅存在于 min 文件内属正常）：
   for n in bootstrap.css bootstrap.rtl bootstrap-grid bootstrap-utilities bootstrap.esm \
            bootstrap.bundle.js bootstrap-reboot all.min.css layui; do
     echo "== $n =="; grep -rn "$n" templates static --include="*.html" --include="*.css" || true
   done
   find static -name "*.map" -delete        # sourcemap 全部可删
   ```
   预期可删：Bootstrap rtl/esm/grid/utilities 全系、非 min 版、全部 `.map`；`static/css/all.min.css`（FontAwesome）与根 `static/js/layui.js` 视上面 grep 结果定——注意 `static/eastmoney-kline/js/layui.js` 是另一份**在用**文件，勿混。
4. **建骨架**：`static/js/{common,pages}`、`static/js/common/{business,components}`、`static/css/{common,pages}`、归档目录，`.gitkeep` 占位。
5. **新增 `static/js/common/utils.js`**：以 `google_sheet/base.html:117-145` 内联脚本为基准搬运三个工具函数（同名同签名，此时尚无引用方，F2 起接入）。
6. **新增 `static/js/common/api.js` 骨架**：请求 helper + `{"status","code","message","data"}` 信封解包 + 非 success 抛错（`02` §3.5）；端点定义先空，F1 试点页起按页迁入。

**回滚**：整批 revert；zip 归档保留在批次 commit 中。

---

## F1 试点批：`google_sheet/merge_export.html`（1 页）

选它因为：526 行、无 `{{ }}` 数据注入（仅 1 处 `{% ` 相关 + url_for）、依赖 `google_sheet/base.html`——正好验证基座展开方法论。

步骤：

1. 截图留底（改造前）；
2. 复制 `google_sheet/base.html` 骨架内联展开到页首，替换其 `url_for`（`03` §2）；**导航暂随基座内联**（navbar.js F2 才首落地，F2 时统一替换为占位）；
3. `{% block content %}` 内容就位；删除 `{% extends %}/{% block %}`；
4. 内联 `<script>` 剪切 → `static/js/pages/google_sheet_merge_export.js`（普通 src，原位置）；
5. 内联 `<style>`（若有）→ `static/css/pages/google_sheet_merge_export.css`；
6. 基座工具函数改引 `common/utils.js`；
7. 该页 fetch 调用迁入 `common/api.js`（**首个端点迁入**，验证 api 层方法论：信封解包、错误提示、`template-auth.js` 拦截链不受影响）；
8. 路由切换（`05` §2.2）：`merge_export` → `send_from_directory`；
9. 验证四件套 → commit。

**附：页面功能验证清单模板（各批复用，按页裁剪）**

- [ ] 首屏渲染与改造前截图一致（含主题/字体）
- [ ] 登录态保持（token 自动附加、401 刷新重放）
- [ ] 权限不足时导航项隐藏（`data-permission` 过滤）
- [ ] localStorage 表单恢复（对应 `*_form_data` 键）
- [ ] 模板回填 / restart 回填（create 族）
- [ ] 轮询刷新（任务日志/进度类页面）
- [ ] 页面专属功能（导出、预览、图表……）
- [ ] `pytest tests/unit tests/integration` 全绿

---

## F2 批：google_sheet 基座族（6 页 + 2 dispatcher）

| 页面 | 特殊点 |
|---|---|
| `google_sheet/index.html` | 导航高亮由 navbar.js 按 URL 计算；`{{request.args.get('version')}}`×2 在 JS 内（按 `03` §5 同法处理）；引用了 CDN bootstrap@5.1.3（保留外链不动，P2 再本地化） |
| `google_sheet/create.html`（C3） | `const TASK_ID` 类常量改为 `URLSearchParams` |
| `google_sheet/detail.html` | 同上 |
| `google_sheet_c31/create.html`（2506 行） | 纯机械搬移；提交后跑 C31 拆分子任务冒烟 |
| `google_sheet/create_dispatcher.html` | **新增**（`03` §4.1），含 `taskTypeToVersion()`（映射原文抄自 `google_sheet.py`）；其 `fetch /api/tasks/<id>` 走 `common/api.js` |
| `google_sheet/detail_dispatcher.html` | 同上 |
| 基座 `google_sheet/base.html` | 本批最后一页完成后：utils 收敛完成 → **导航条迁入 `common/components/navbar.js`（首个组件，F2 首落地：本族 5 页导航替换为 `<div data-navbar></div>`，渲染产物与原基座逐字节一致，`02` §3.7）** → 删除基座文件 |

本批全部页面统一动作：`<nav>` 占位替换、common 脚本按序引入（`template-auth.js` → `navbar.js` → `api.js` → `utils.js` → 页面 JS）；页面 fetch 调用迁入 `common/api.js`。

路由同步切换（`05` §2.2/§2.3）：`/`、`/create`、`/detail` 改为按 version 分发 + 无 version 落 dispatcher。

> 2026-09-08 已执行：F2 四页（index/create/detail/c31 create）静态化完成，base.css 抽出、基座 base.html 已删，api.js 新增 config/task×10/template×3/googleSheet×4/export.task 端点；遗留：create.js 两个 return; 后不可达乱码头（含字面 fetch）按搬移纪律原样保留待 F6 清扫，importToken 成功 toast 因信封解包改显页面内字面量（原显示信封 message），c31 的 template_id 条件块经核实为服务端从未注入的死代码已按渲染结果移除。

---

## F3 批：c4/c5/c7 六大页（6 页）

顺序：每版先 `create` 后 `detail`（create 相对独立，detail 含 §5 高危点）。

| 页面 | 行数 | 特殊点 |
|---|---|---|
| c4/create, c5/create, c7/create | 2335/2567/2801 | 机械搬移；`*_form_data` localStorage 恢复逐键验证 |
| c4/detail | 2510 | 机械搬移 |
| c5/detail, c7/detail | 2497/2636 | **JS 模板字符串内 `{{ version }}` ×4**（`03` §5），`CURRENT_VERSION` 常量就位后逐处替换 |

验证重点：restart 回填（detail → create 带 `restart_task_id` 跳转）、K 线自定义模式（custom）字段、取消任务按钮。

**批内收敛 pass**（搬移全部过验证后执行，`02` §3.6 两步走；每个收敛域一个 `dedupe` commit，独立可 revert）：

- create 三胞胎共同逻辑（表单状态 localStorage 恢复/保存、参数展开校验、提交组装）→ `common/business/`（建议模块：`form-state.js`、`task-submit.js`）；
- detail 三胞胎共同逻辑（任务详情轮询、日志面板刷新、restart 回填跳转）→ `common/business/`（建议模块：`task-polling.js`、`restart-restore.js`）；
- 页面差异留在 `pages/*.js`（版本号、字段映射、专属按钮）；
- 收敛后每页重跑验证四件套，重点回归 localStorage 各键与 restart 回填。

> 2026-09-08 已执行：F3 六页（c4/c5/c7 create+detail）静态化完成。de-Jinja：三 create 的 `{% block styles %}`（5-111）确认为死代码未搬移；c5/c7 create 的 `{% if template_id %}` 死代码块按渲染结果删除；c5/c7 detail JS 模板字符串内 `{{ version }}`×4 改 `${CURRENT_VERSION}`；6 处 `url_for(...index...)` 改字面量 `/google-sheet/?version=<默认>` + 页面 JS 按 `versionParam` 运行时改写返回链接。api 收口（D9）：全部 46 处 fetch/ajaxRequest 迁入 `Api.endpoints.*`（meta/config/task/template/googleSheet/export 既有端点，新增 `export.taskStocks` 供 c7 按股票代码 ZIP 导出），无遗留字面 fetch；ajaxRequest 回调按 F2 同法改 promise，`err.message` 即原信封 message。detail 三页 scripts 块内真实 `<style>`（结果表格样式）原样抽离为 `static/css/pages/google_sheet_c<4|5|7>_detail.css`。收敛 pass：三胞胎规范化后逐字相同的函数提升至 `common/business/`——create→`form-state.js`(13)+`task-submit.js`(5)，detail→`task-polling.js`(16)+`config-edit.js`(10)，页面调用点（含静态 HTML onclick、函数引用传参、`window.openEditConfigModal` 桥）全部改写 `Biz.*`；规范化有差异的函数全部保留在 pages 层（create 21 个：saveFormData/loadSavedFormData/clearSavedFormData/calculateCombinations/submitTask/fillFormWithTemplate/getCurrentConfig/loadTemplates/loadWorksheetsForItem/normalizeC4Config 等；detail 6 个：loadTaskDetail/groupResults/flattenResults/renderResults/loadTaskConfig/loadTaskParameters）。测试：test_static_pages 13 passed（新增 6 条登记）；全量 `pytest tests/unit tests/integration` 568 passed / 7 failed 均为既有基线（kline_adjustment×1、kline_sheet_guardrails×1、charts×4、value_parser×1）/ 10 skipped，无新增失败。
>
> 2026-09-08 重做注记：本批随后再次遭遇工作区事故，6 个输出页（templates + pages JS/CSS）被回退为 Jinja（routes 回 `render_template`、test 登记再注释），但共享产物 `common/business/form-state|task-submit|task-polling|config-edit.js` 与 `common/api.js` 幸存。本次重做完整复用幸存产物：转换器 `_f3_convert.py`（按现 HEAD 模板含 092414f 的 `data.data` 取数路径适配断言）与收敛器 `_f3_dedupe_apply.py` 原样重放，6 页一次性通过全部断言；de-Jinja 改写、api 收口（60 处 fetch/ajaxRequest 调用行迁 `Api.endpoints.*`，端点零新增——`export.taskStocks` 等均已就位）、detail CSS 抽离（与原 `<style>` 块逐字节一致）、Biz 接线（含函数引用传参 `importGoogleSheetToken`×3、`filter(shouldShowDetailMetric)`×6、`window.openEditConfigModal` 桥×3）与首次完成版一致。routes：google_sheet.py 6 分支 `render_template` → `send_page`（`render_template` import 随之移除）；test_static_pages 恢复 F3 6 条登记并删除事故注记，45 passed；全量 600 passed / 7 failed 均为既有基线 / 10 skipped，无新增失败；6 个 pages JS 过 `node --check`。转换器脚本已按约定删除。

---

## F4 批：backtest 双胞胎 + global_preview（11 页）

| 页面 | 特殊点 |
|---|---|
| bt/multi 各自 `create`、`list` | `list` 页 `tasksPerPage`、分页重绘；bt/multi create 函数相似度仅 14%，**各自独立搬移，禁止互相参考改写** |
| bt/multi `detail/<task_id>` | task_id 改路径正则解析 |
| bt/multi `global_preview/<task_id>` | 同上 |
| bt/multi `result/<result_id>` | **task_id 推导前端化**（`03` §4.3）：先核对 `/api/task-result/<id>` 响应字段 |
| bt `result_export_preview` | result_id 路径解析 |
| `global_preview/index.html` | 机械搬移 |

**批内收敛 pass**（`02` §3.6；`dedupe` commit 独立可 revert）：bt/multi `list`、`result` 双胞胎 92% 相同部分（任务列表分页重绘 `tasksPerPage`、结果表格渲染）→ `common/business/`。bt/multi `create` 函数相似度仅 14%，**保持各自独立，禁止强行合并**。收敛后重跑验证四件套。

> 2026-09-09 已执行：F4 十二页（backtest_training 六页 + backtest_multi_product 五页 + global_preview/index）静态化完成。基座展开：admin/base.html 逐字节内联展开（大块内联 style 保留在页头不动，页面 style 原样抽离为 `static/css/pages/backtest_*_*.css`；`data-auth-enabled` 已删 D3；侧栏脚本(:408-478)收敛为 `static/js/common/admin-shell.js`，脚本序 template-auth → admin-shell → trading-date → api → utils → business → pages）。de-Jinja（`03` §3 #1-3）：detail/global_preview 的 `{{ task_id }}` 展示位（taskIdText/summaryTaskId）改空占位 + 页面 JS 顶部 `location.pathname` 正则解析运行时填充，backToDetailLink/globalPreviewLink href 同法；`{{ task_id|tojson }}`×4、`{{ result_id|tojson }}`×3 同法解析；result 页 task_id 按 §4.3 改从 `/api/task-result/<id>` 响应 `word_report_payload.task_id` 推导（核对 backtest_api.py 属实；缺失时按空串处理，与原类型不匹配降级一致），result 页路由的 `resolve_result_task_id` 查询删除；result 页 scripts 块 `{{ super() }}` 核实为基座空 block 渲染为空、未搬移。路由：backtest_training.py / backtest_multi_product.py / global_preview.py 共 15 处 `render_template` → `send_page`（`05` §2.2），路由路径与装饰器不变。api 收口（D9）：46 处 fetch/ajaxRequest 全部迁入 `Api.endpoints.*`——新增 `backtest` / `backtestMulti` / `previewHub` / `stock` 域与 `export.{globalPreview,globalPreviewsBatch,backtestResult,backtestResultXpl,wordReport}`（文件流端点照旧返回原始 Response）；api.js 增量能力：request 支持 `options`（如 AbortController `signal`）与 FormData 上传、`Api.envelope()` 返回完整信封供 postTaskAction 保留成功 toast 的服务端 message，wire 格式零变化，页面零字面 fetch。收敛 pass（dedupe）：list 双胞胎 9 个函数 → `common/business/task-list.js`、result 双胞胎 39 个 → `result-table.js`（`window.Biz` 命名空间，模块内 IIFE 本地绑定保证函数间调用与原实现一致；页面调用点含模板字符串内插值全部改写 `Biz.*`；规范化有差异或引用页面状态的函数（如 renderPagination/updateStatistics/renderBatchExportTaskList/getTaskSecondaryText 等）按纪律保留在 pages 层）；create 双胞胎保持独立。信封解包顺带修复三处 B2 信封改造未同步的页面适配缺口（bt/multi create 成功分支 `data.task_id` 判断恢复生效→创建成功重新跳转列表；bt global_preview `previewPayload` 恢复读真实载荷；list 指标卡 `updateStatistics` 恢复读全局 statistics），均为客户端解包等价改写的结果，未改任何 API。测试：test_static_pages 25 passed（新增 12 条登记）；全量 `pytest tests/unit tests/integration` 580 passed / 7 failed 均为既有基线（kline_adjustment×1、kline_sheet_guardrails×1、charts×4、value_parser×1）/ 10 skipped，无新增失败。F6 遗留：① detail 页 postTaskAction 以 `Api.envelope(URL)` 收口，URL 仍由页面 `TASK_API_BASE` 常量拼接（fetch 本体已在 api.js）；② result 页 fillRepairDaysTable 的 return 后不可达段、fillKamaTable/fillSharpeTable 无调用方等死代码按搬移纪律原样保留；③ result CDN chart.js 保留外链（P2）。

---

## F5 批：admin 13 页 + 独立页 7 页（20 页）

| 组 | 页面 | 特殊点 |
|---|---|---|
| admin 简单页 ×10 | config/navigation/logs/templates/results/model-summary/eastmoney-kline/scheduler/users/roles | 机械搬移 + `admin-shell.js` 接入 |
| admin/tasks.html | 1366 行 | **4 组 `<option>` Jinja 循环**改 `/api/meta/enums` 渲染（`03` §3 #9） |
| admin/google_sheets.html | | 同上 ×2 + tojson（#7/#8） |
| admin/dashboard.html | | CDN chart.js 保留外链 |
| xpl ×3 | index/v1/v2 | v1/v2 大页机械搬移；jquery CDN 保留 |
| yule ×2 | index/sjxz | sjxz 独立页：删 `data-auth-enabled`；CDN（tailwind JIT/gsap/swiper）保留，P2 再议 |
| eastmoney_kline/index | | 已模块化，仅 url_for → 字面量 + JS 抽离 |
| login.html | | `next_url` → JS 填充（`03` §3 #5）；删 `data-auth-enabled` |
| 基座 `admin/base.html` | | admin 族全部完成后：admin 菜单变体并入 `navbar.js` → 删除基座文件 |

> 2026-09-08 已执行：F5 十九页（admin 13 + xpl 3 + yule 2 + login + eastmoney_kline/index；yule/index 为 3 行跳转壳）静态化完成。基座展开：admin/base.html 逐字节内联展开（head 4 处 url_for → 字面量、大块内联 style 原样保留页头、`{% block head %}` 页面 style 抽离为 `static/css/pages/admin_*.css` 并原位 `<link>`、`data-auth-enabled` 已删 D3、侧栏脚本(:408-478)改引 `common/admin-shell.js`、脚本序 template-auth(?v=20260415_page_scope) → admin-shell → trading-date → api → utils → pages）。de-Jinja（`03` §3 #9/#7/#8、§4.4）：admin/tasks 4 组 `<option>` 循环与 admin/google_sheets 2 组循环 + tojson 改 `/api/meta/enums` 客户端渲染（渲染函数在 admin_tasks.js / admin_google_sheets.js 原位；字段名核对 `meta_api.py`：`task_statuses`/`task_types`/`task_status_editable`/`google_sheet_table_types`；`GOOGLE_SHEET_TABLE_TYPE_OPTIONS` 由 const 改 let 以便枚举异步回填；filter 用同一 `task_types`，即 `model_summary_rebuild` 系统类型不再出现在筛选下拉，为 `03` 明示契约）；admin/templates 4 处 url_for → 字面量（3 锚点 + `const baseUrl = "/google-sheet/create"`）；admin/eastmoney-kline iframe src → `/eastmoney-kline`；admin/dashboard 路由上下文（counts/recent_tasks）核实为模板未消费的死注入，随 send_page 一并消失。xpl/index 的 `{% block style %}` 为死代码（基座无 style block，`03` §8.1 判例）未搬移；xpl v1/v2 head style 抽离为 pages css；`{{ super() }}`×3 核实为空 block 渲染为空删除；CDN（jquery/datatables/chart.js/xlsx-js-style）保留外链。yule/sjxz 删 `data-auth-enabled`、保留 `data-template-auth-floating-nav`/`expose-helpers`，内联 style/script 抽离；login `loginNextUrl` 改 `login.js` 运行时从 `?next=` 填充（`03` §3 #5）；eastmoney_kline/index 6 处 url_for → `/static/eastmoney-kline/...` 字面量（layui.css/layui.js 指向文件今日仍不存在，按指令原样保留），内联 script/style 抽离为 pages 层。路由：admin.py 13 处、xpl.py 3 处、yule.py 2 处、auth_pages.py 1 处、eastmoney_kline.py 1 处 `render_template` → `send_page`，路径与装饰器不变、死上下文删除。**导航条合并（D6'）**：28 页（admin 13 + xpl 3 + bt 6 + multi 5 + global_preview 1）侧栏外壳经程序化比对逐字节一致 → `navbar.js` 新增 admin 族（挂载点即 `<nav class="sidebar ..." data-navbar>`，渲染保留原 class；菜单仍由 template-auth.js 填 `#templateSidebarMenu`、active 按 pathname+search），各页导航整段替换为占位，navbar.js 插入 template-auth 之后、admin-shell 之前。`templates/admin/base.html` 于零引用核实后 `git rm`（zip 归档留底）。**F5 事故与恢复（重要）**：本批执行中一次 `git checkout -- templates/` + `git clean` 误将整个未提交工作区（F1~F4 静态页与 pages JS/CSS 从未 commit）回退/删除；经 ZCode 会话库（db.sqlite 工具调用链）逐 op 重放 + Temp 目录幸存的 `f4_build.py`/`f4_dedupe.py`，F1/F2/F4 已恢复并通过 test_static_pages 全量登记；**F3 六大页（c4/c5/c7 create+detail）静态版与其转换期输入不可恢复**——转换器对现 HEAD 模板的多处 rep/scoped 断言不匹配（HEAD 含 F3 之后提交的接口取数修复），已回退为 `render_template`（Jinja）继续服务并同步回退 google_sheet.py 对应 6 个分支、test_static_pages 暂注销 6 条（文件头有事故注记），待按 `03`/`04` F3 章节重做（`common/business/form-state|task-submit|task-polling|config-edit.js` 仍在）。测试：test_static_pages 45 passed（新增 20 条登记：admin 13 + xpl 3 + yule 2 + eastmoney-kline + login；独立页条目带 require_common_scripts=False 标志）、test_xpl_v2_page 改为 HTML+pages JS 双侧断言；全量 `pytest tests/unit tests/integration` 594 passed / 7 failed 均为既有基线（kline_adjustment×1、kline_sheet_guardrails×1、charts×4、value_parser×1）/ 10 skipped，无新增失败；38 个 pages JS + navbar.js 全部过 `node --check`。F6 遗留：① admin 族页面 fetch 仍走 template-auth.js 的 ajaxRequest（D9 收口未做，机械搬移豁免）；② c4/c5/c7 六页 F3 已于同日重做完成（见 F3 批重做注记）；③ eastmoney_kline/index 引用的 layui.css/layui.js 缺文件、各 CDN 外链本地化（P2）。

---

## F6 收尾批（0 页改造）

1. 全库路由终检：37 条页面路由全部 `send_from_directory`，无 `render_template` 残留：
   ```bash
   grep -rn "render_template" app/routes --include="*.py"    # 期望无输出
   grep -rn "{{\|{%" templates --include="*.html"            # 期望无输出
   ```
2. fetch 出口终检（B 修订，`02` §3.5）：
   ```bash
   grep -rn "fetch(" static/js/pages --include="*.js"        # 期望无输出（全部经 common/api.js）
   grep -rln "fetch(" static/js/common/*.js                  # 仅允许 template-auth.js（拦截器）与 api.js
   ```
3. 删除 `_resolve_task_version()`（已被 dispatcher 取代，`03` §4.1）；
4. `template-auth.js` 删除 `data-auth-enabled` 读取分支（此时 4 处注入属性已全部消失）；
5. AGENTS.md 更新：前端章节（目录约定、pages/api/business/components 分层、dispatcher、双部署入口指向本目录文档）；
6. 双部署验收（`05` §8 清单）；
7. 合并分支，zip 归档随仓库保留。

## 回滚策略

| 层级 | 操作 |
|---|---|
| 单页 | `git revert <该页 commit>`（每页独立 commit 的意义） |
| 批次 | 分支不合并即可；已合并则 revert merge commit |
| 整体 | `templates-jinja-source.zip` 是最终兜底（解包覆盖即回到 Jinja 版，配合 `render_template` 路由） |

> **2026-09-08 F6 执行记录**：三组终检全过——`grep render_template app/routes` 零输出（37 条页面路由全部 `send_page`）；`grep "{{\|{%" templates` 零输出；`grep "fetch(" static/js/pages` 零输出（最后 34 处 admin/xpl 站点已迁入 `common/api.js`，xpl 域含 CSRF 头保持 wire 等价）；`data-auth-enabled` 全库消失，`template-auth.js::isAuthEnabled` 按 D3 恒返回 true；`_resolve_task_version()` 已删除；AGENTS.md"双前端"章节更新为静态化分层约定。全量回归 600 passed / 7 failed（全部既有基线）/ 10 skipped。`test_xpl_v2_page` 的 1 条旧 URL-in-JS 断言按新契约更新（URL 移入 api.js，页面断言 `Api.endpoints.stock.search`）。
