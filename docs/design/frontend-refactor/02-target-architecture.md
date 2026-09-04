# 02 — 目标架构与规范

> 原则：无构建链、无框架、无兼容层。唯一准绳是仓库内已验证可行的 `static/eastmoney-kline/js/` 模块化样板（普通 `<script src>` 按序引入 + 目录分层）。

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
    common/                        # 新增：跨页共享收敛
      utils.js                     # sanitizeJSONString / parseJsonArray / extractSpreadsheetId
                                   #（google_sheet/base 内联脚本 + ≥6 页复制粘贴收敛于此，同名同签名）
      admin-shell.js               # admin/base 内联的侧栏折叠脚本（仅 admin 页引入）
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
- `common/` 只收敛"已经存在于 ≥2 处的完全相同代码"，不做提前抽象；
- `templates/` 内**零 Jinja 语法**（`03` 逐条对照），每个页面是完整 HTML 文档；
- `pages/*.js` 与页面**一一对应**，禁止一个 JS 服务多页（那是后续去重立项的事）。

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
  <!-- 导航条：原 base.html 的 <nav> 原样内联，active 类由 template-auth.js 按 URL 判定 -->
  <div class="container mt-4" data-template-main-content>
    <!-- 原 {% block content %} 内容 -->
  </div>
  <script src="/static/js/common/template-auth.js"></script>
  <script src="/static/js/common/utils.js"></script>
  <script src="/static/js/pages/google_sheet_create.js"></script>             <!-- 原内联 script -->
</body>
</html>
```

要点：

1. **body 上删除 `data-auth-enabled`**（`isAuthEnabled()` 对缺失属性返回 true，行为即"鉴权开启"）；
2. **导航高亮**：原 Jinja `{% if request.args.get('version') == 'c3' %}active{% endif %}` 改由 `template-auth.js` 按 `location.pathname+search` 判定后加 class（逻辑等价迁移，一处实现）；
3. 内联 `<style>` 是否抽离为 pages CSS：**抽离**（统一归位），文件名与页面对应；内容不改一个字节。

## 3. JS 规范

### 3.1 分层

| 层 | 位置 | 职责 | 禁止 |
|---|---|---|---|
| vendor | `static/vendor/` | 第三方原版 | 任何修改 |
| common | `static/js/common/` | 鉴权、fetch 包装、纯工具函数 | 业务逻辑、DOM 选择器（auth 的导航过滤除外） |
| pages | `static/js/pages/` | 单页全部业务逻辑 | 跨页复用（发现重复 → 提升到 common，需两个页面都在用） |

### 3.2 加载与执行时序契约（本次最高风险点，强制）

- 抽离的页面 JS 一律用**普通 `<script src>`（无 `defer`/`async`/`type="module"`）**，且**放在与原内联脚本相同的文档位置**；
- 理由：内联脚本是解析到即同步执行的，页面里存在"前一个脚本定义全局函数、后一个脚本/DOM 立即使用"的顺序依赖；改 module/defer 会把执行推迟到文档解析完，初始化时序变化可能破坏 localStorage 恢复、模板回填等启动逻辑；
- 页面 JS 之间的依赖顺序 = 原文档中 `<script>` 块的出现顺序；
- 例外：确认仅操作 DOMContentLoaded 回调的脚本，仍保持普通 script（统一规则，不留双态）。

### 3.3 代码风格

- 不引入打包器/TS/新语法降级诉求；沿用各页现有 ES5~ES2018 风格，**搬移不改写**；
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

1. 不引入 npm/webpack/vite/import maps —— 无构建链是硬约束；
2. 不把页面 JS 合并/去重（c4/c5/c7、backtest 双胞胎的 90% 相似是历史债，另行立项）；
3. 不改 DOM 结构、class、id（`data-*` 属性仅删除 `data-auth-enabled` 一个）；
4. 不改任何 API 的请求/响应；
5. 不在本次引入 `common/api.js` 统一 fetch 封装（各页现有 ajax 写法保留；统一封装留给后续治理）。
