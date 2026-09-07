# 02 — 目标架构与规范

> 原则：无构建链、无框架、无兼容层。唯一准绳是仓库内已验证可行的 `static/eastmoney-kline/js/` 模块化样板（普通 `<script src>` 按序引入 + 目录分层）。
>
> **2026-09-07 修订（B 方案）**：在原"只搬移不改写"基础上纳入统一三层——接口层 `common/api.js`、业务共享层 `common/business/`、组件层 `common/components/`（导航条组件化，D6 由"内联展开"改为"组件渲染"）。分层形状与 `frontend/src/{api,composables,components}` 对齐，降低后续 Vue 迁移翻译成本。仍然零框架、零构建链，统一三层都是普通 script 文件。

## 1. 目标目录结构

```
templates/                         # 目录名不变（D8）。F0 先整体 zip 归档原 Jinja 版，此后就地静态化
  login.html                       # 独立页（无基座）
  admin/                           # 13 页；base.html 在该族最后一页完成后删除
  google_sheet/                    # index/create/detail/merge-export + 2 个 dispatcher 页（见 05 §2.3）
  google_sheet_c31/ google_sheet_c4/ google_sheet_c5/ google_sheet_c7/
  backtest_training/ backtest_multi_product/
  xpl/ yule/ eastmoney_kline/ global_preview/
static/
  js/
    template-auth.js               # 保留原路径不动（跨批次引用安全，见下）
    trading-date.js                # 保留原路径不动
    common/                        # 跨页共享收敛
      api.js                       # 统一接口层：全部端点定义 + 请求 helper（§3.5）
      utils.js                     # sanitizeJSONString / parseJsonArray / extractSpreadsheetId
                                   #（google_sheet/base 内联脚本 + ≥6 页复制粘贴收敛于此，同名同签名）
      admin-shell.js               # admin/base 内联的侧栏折叠脚本（仅 admin 页引入）
      business/                    # 跨页共享业务逻辑（§3.6）：任务轮询、表单恢复/回填等
      components/                  # 可复用 DOM 组件（§3.7）：navbar.js 首个落地
    pages/                         # 每页一个 JS，文件名 = 模板名（一一对应）
      google_sheet_create.js
      google_sheet_c7_create.js
      backtest_training_detail.js
      ...
  css/
    common/                        # template-auth.css 迁入；可选 base.css（仅当多页内联 style 逐字节相同时）
    pages/                         # 每页内联 <style> 原样抽离，文件名对应
  vendor/                          # 第三方库归位（bootstrap.min.{css,js}、bootstrap-icons、layui、
                                   #  eastmoney-kline/ 保持现状）；F0 删除未引用变体（04 §F0）
```

规则：

- `template-auth.js` / `trading-date.js` **不迁移**：静态化是逐批进行的，未改造页面仍引用旧路径，中途移动会造成两态引用；它们本来就在 `static/js/` 下，语义上就是 common，保留原路径（F6 收尾时可视情况归入 `common/`，属可选整理）；
- `common/`（含 `business/`、`components/`）提升门槛仍是"存在于 ≥2 处的相同代码"；区别在于 **c4/c5/c7 与 backtest 双胞胎的去重是本方案明示目标**（原"另行立项"已并入，见 D9），不再是发现多少算多少；
- `templates/` 内**零 Jinja 语法**（`03` 逐条对照），每个页面是完整 HTML 文档；
- `pages/*.js` 与页面**一一对应**：页面独有逻辑留在 pages 层，跨页共同逻辑收敛到 business 层后 pages 层只保留"调用 + 页面差异参数"。

## 2. HTML 页面骨架规范

静态化后的每页结构（以 google_sheet 族为例，标记与现有 base.html 逐字节一致）：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>…</title>
  <link href="/static/css/vendor/bootstrap.min.css" rel="stylesheet">
  <link href="/static/font/bootstrap-icons.css" rel="stylesheet">
  <link href="/static/css/common/template-auth.css" rel="stylesheet">
  <link href="/static/css/pages/google_sheet_create.css" rel="stylesheet">   <!-- 原内联 style -->
  <script src="/static/js/vendor/bootstrap.bundle.min.js"></script>
</head>
<body class="template-auth-pending">
  <!-- 导航条：占位容器，由 common/components/navbar.js 渲染（渲染产物与原基座导航逐字节一致，D6 修订） -->
  <div data-navbar></div>
  <div class="container mt-4" data-template-main-content>
    <!-- 原 {% block content %} 内容 -->
  </div>
  <script src="/static/js/common/template-auth.js"></script>
  <script src="/static/js/common/components/navbar.js"></script>
  <script src="/static/js/common/api.js"></script>
  <script src="/static/js/common/utils.js"></script>
  <script src="/static/js/pages/google_sheet_create.js"></script>             <!-- 原内联 script -->
</body>
</html>
```

要点：

1. **body 上删除 `data-auth-enabled`**（`isAuthEnabled()` 对缺失属性返回 true，行为即"鉴权开启"）；
2. **导航条组件化（D6'）**：原基座内联的 `<nav>` 整段替换为 `<div data-navbar></div>` 占位；`navbar.js` 内置三族菜单配置，按 `location.pathname` 前缀选族渲染，active 类按 `location.pathname+search` 判定（取代原 Jinja `{% if request.args.get('version') == 'c3' %}active{% endif %}`，逻辑等价迁移，一处实现）；
3. **navbar.js 时序契约**：普通 `<script src>`（无 defer/async/module），放在 `template-auth.js` 之后同步执行；此时 body 仍带 `template-auth-pending`（内容未揭示），导航渲染完成早于鉴权揭示，**无首屏闪动**——这是 D6 可以从"内联展开接受重复"升级为"组件化"的可行性依据；
4. common 脚本引入顺序固定：`template-auth.js`（fetch 拦截器，必须最先）→ `navbar.js` → `api.js` → `utils.js` → 页面 JS；
5. 内联 `<style>` 是否抽离为 pages CSS：**抽离**（统一归位），文件名与页面对应；内容不改一个字节。

## 3. JS 规范

### 3.1 分层

| 层 | 位置 | 职责 | 禁止 |
|---|---|---|---|
| vendor | `static/vendor/` | 第三方原版 | 任何修改 |
| common | `static/js/common/` | 鉴权（template-auth.js，原路径）、纯工具函数（utils.js）、侧栏（admin-shell.js） | 业务逻辑、DOM 选择器、发请求 |
| api | `static/js/common/api.js` | **全部后端端点定义 + 请求 helper**（§3.5） | 页面各自手写 fetch URL |
| business | `static/js/common/business/` | 跨页共享业务逻辑：任务轮询、表单恢复/回填、分页表格等（§3.6） | 单页专属逻辑、样式 |
| components | `static/js/common/components/` | 可复用 DOM 片段渲染：导航条、模态框等（§3.7） | 依赖页面全局变量、数据绑定 |
| pages | `static/js/pages/` | 单页业务逻辑：调用 api/business，只保留页面差异 | 手写 fetch URL、复制 business 已有逻辑 |

### 3.2 加载与执行时序契约（本次最高风险点，强制）

- 抽离的页面 JS 一律用**普通 `<script src>`（无 `defer`/`async`/`type="module"`）**，且**放在与原内联脚本相同的文档位置**；
- 理由：内联脚本是解析到即同步执行的，页面里存在"前一个脚本定义全局函数、后一个脚本/DOM 立即使用"的顺序依赖；改 module/defer 会把执行推迟到文档解析完，初始化时序变化可能破坏 localStorage 恢复、模板回填等启动逻辑；
- 页面 JS 之间的依赖顺序 = 原文档中 `<script>` 块的出现顺序；
- 例外：确认仅操作 DOMContentLoaded 回调的脚本，仍保持普通 script（统一规则，不留双态）。

### 3.3 代码风格

- 不引入打包器/TS/新语法降级诉求；沿用各页现有 ES5~ES2018 风格，**搬移阶段不改写**（收敛阶段的受控改写见 §3.6 两步走纪律）；
- 全局命名空间：页面 JS 允许继续使用现有全局函数名（不动）；新增 common 工具挂 `window` 原有名字，保证调用点零修改；
- `common/utils.js` 中函数名必须与被收敛的复制粘贴版本**同名同签名**（以 google_sheet/base.html 内联版为基准，冲突时以大多数页面一致者为准并逐页核对调用点）。

### 3.4 服务端数据获取规则（替代 Jinja 注入）

| 原注入 | 新获取方式 | 时机 |
|---|---|---|
| `task_id` / `result_id`（路径或 query） | `location.pathname` 正则 / `URLSearchParams` | 页面 JS 顶部（原 `const TASK_ID = …` 位置） |
| `version` | `URLSearchParams.get('version')` | 同上 |
| `next_url`（login 隐藏域） | `URLSearchParams.get('next')` | login 页 JS |
| 枚举（6 处 option 循环 + 1 处 tojson） | `GET /api/meta/enums`（已存在、免登录） | DOMContentLoaded 后渲染 `<option>`，渲染代码放在对应原位置 |
| `auth_enabled` | 删除（D3） | — |

### 3.5 接口层（common/api.js，B 修订新增）

- **唯一出口**：全部 `/api/*` 请求必须经 `api.js`；`pages/*.js` 禁止出现字面量 fetch URL。豁免仅两处：`template-auth.js`（拦截器本体，负责 token 附加与 401 刷新重放）与 dispatcher 页（新建，见 `03` §4.1，其请求同样走 api.js 后豁免即消失）；
- **传输不重复造**：鉴权传输已由 `template-auth.js` 全局拦截 fetch 实现，api.js 不碰 token/刷新逻辑，只做：端点常量（按域分组：`googleSheet / task / backtest / admin / auth / meta …`，分域命名对齐 `frontend/src/api/*.js`）+ `request(method, path, body)` + 统一响应信封解包（`{"status","code","message","data"}`，非 success 抛错并把 `message` 交给调用方/toast）；
- **wire 格式零变化**：api.js 只收敛调用方代码，不改变任何请求/响应内容（原红线保持）；
- 单文件起步；超过 ~500 行再按域拆 `common/api/<域>.js`，`api.js` 保持唯一聚合入口（页面仍只引一个 `<script>`）。

### 3.6 业务共享层（common/business/，B 修订新增）

- **两步走纪律（强制）**：每页先机械搬移（保持 §3.2 时序契约，`de-jinja` commit）→ 当批验证四件套通过 → 批内收敛 pass（把双胞胎共同逻辑提升为 business 模块并改写页面调用点，`dedupe` commit）→ 再次验证。两个 commit 分离，单页/单域均可独立回滚——这是收敛改写不破坏"搬移可回滚"的关键；
- **明示收敛对象**：c4/c5/c7 create 三胞胎（相似度 91%）、三 detail、backtest 双胞胎 list/result（92%）。候选模块：任务轮询、`*_form_data` localStorage 恢复/模板回填/restart 回填、K线选项加载、分页表格重绘；
- business 模块挂 window 命名空间（如 `Biz.taskPolling`），页面调用点显式改写；"同名同签名"要求仅适用于 `utils.js`（历史复制粘贴收敛），business 模块允许重新设计签名；
- 菜单、枚举等"数据型共享"不进 business：来自后端的走 api.js（`/api/meta/enums` 等），纯前端常量放各模块顶部。

### 3.7 组件层（common/components/，B 修订新增）

- **navbar.js（首个组件，F2 首落地）**：三套基座的导航条合一。渲染函数 + 内置三族菜单配置（admin / google_sheet 族 / 独立页），按 `location.pathname` 前缀选族；页面 HTML 中基座导航整段替换为 `<div data-navbar></div>`；
- **渲染等价红线**：渲染产物 DOM（结构/class/属性顺序）与原基座导航逐字节一致，active 计算结果也一致；nav 相关 CSS 选择器零改动。"DOM 零改动"红线在导航处放宽为"**渲染后等价**"（源 HTML 允许占位替换）；
- 其他组件按"≥2 处完全相同的 DOM+JS 片段"提升（候选：确认模态框、分页条），**只做渲染函数 + 模板字符串，不做数据绑定**（不造微型框架）；
- 组件禁止读取页面全局变量；参数经 `data-*` 属性或初始化函数传入；渲染时机必须早于鉴权揭示（见 §2 要点 3）。

## 4. CSS 规范

- `vendor/`：Bootstrap 只保留 `bootstrap.min.css`、`bootstrap-reboot.min.css`（若有引用）、`bootstrap-icons`（`static/font/`）；**删除 rtl / grid / utilities / esm / 非 min / `.map` 变体**——删除前逐个 grep 全库（含 `templates/` 与 `static/`）确认零引用（清单见 `04` §F0）；
- `common/`：`template-auth.css` 迁入；如多页存在逐字节相同的内联 style 片段（如 body 背景阴影段），收敛为 `base.css`，**仅限完全相同片段**；
- `pages/`：每页内联 style 原样抽离，不改选择器、不改值；
- 命名：文件名 = 页面模板名（`google_sheet_c7_create.css`）。

## 5. 缓存与版本化策略

| 资源 | 策略 |
|---|---|
| HTML（templates/ 下页面） | `Cache-Control: no-cache`（内容变了立即生效） |
| `/static/**` | nginx `expires 30d` + `immutable`；Flask 模式用 `SEND_FILE_MAX_AGE_DEFAULT` |
| 版本失效 | 沿用现有 `?v=` 约定：发布时统一替换页面里引用的 `?v=<release>`（当前仅 template-auth.js 有 `?v=20260415_page_scope`，改造后所有 common/pages 资源都带） |
| 可选增强 | nginx `open_file_cache`；不强制 content-hash 重命名（无构建链，手工 hash 维护成本 > 收益） |

> `template-auth.js` / `trading-date.js` 保留原路径（§1 规则），各页引用 URL 不变，不存在跨批次迁移问题；仅其内容改动（删除 `data-auth-enabled` 读取）随所在批次的页面一起生效。

## 6. 明确不做的事

1. 不引入 npm/webpack/vite/import maps —— 无构建链是硬约束（统一三层是普通 script 文件，不是模块系统）；
2. 不引入 Vue/React/任何框架 —— components 层是"渲染函数 + 模板字符串"，不是响应式框架，不做数据绑定；
3. 不改任何 API 的请求/响应 —— api.js 只收敛调用方，wire 格式零变化；
4. DOM 改动仅限两处明示点：① 删除 `data-auth-enabled`；② 导航条整段替换为 `<div data-navbar></div>` 占位（渲染产物逐字节等价，§3.7）。其余 DOM 结构、class、id 零改动；
5. 跨页 CSS 不做去重设计（pages CSS 抽离保持原样；样式收敛另行立项）。

> 原条目"不合并双胞胎页面"、"不引入 common/api.js 统一 fetch 封装"已由 2026-09-07 B 修订废止：接口/业务/组件统一纳入本方案（README §4 D9），执行方式见 §3.5~§3.7 与 `04` 各批"收敛 pass"。
