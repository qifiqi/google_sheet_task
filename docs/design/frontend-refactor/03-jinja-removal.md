# 03 — 模板语法移除对照

> 本文是全库 Jinja 语法（`{{ }}` / `{% %}`）与服务端页面逻辑的**穷举清单**及逐条替换方案。执行任何批次前，先按 `grep` 命令重新核对本清单的完整性（见 §7）。

## 1. 总则

1. **DOM 与视觉零改动**：所有替换只发生在"属性值、文本占位、脚本内容"层面，不增删 DOM 节点、不改 class/id；
2. **替换优先用运行时信息**（URL 参数、已有 API），杜绝在页面里写死环境相关值；
3. 每条替换完成后，该页不得再有任何 `{{` 或 `{%` 字符（验收 grep 见 §7）。

## 2. `url_for` 替换规则

### 2.1 静态资源（机械替换）

```
{{ url_for('static', filename='css/bootstrap.min.css') }}  →  /static/css/vendor/bootstrap.min.css
{{ url_for('static', filename='js/template-auth.js') }}?v=…  →  /static/js/template-auth.js?v=…
```

> 路径中的 `vendor/`、`css/common/`、`css/pages/` 归位以 `02` §1/§4 为准，F0 完成 vendor 归位后统一替换。

### 2.2 页内链接（endpoint → 字面量）

| Jinja | 字面量 |
|---|---|
| `url_for('google_sheet.index', version='c3'/'c4'/'c5'/'c7'/'c31')` | `/google-sheet/?version=c3` 等 |
| `url_for('google_sheet.index', version=request.args.get('version'))` | `href="/google-sheet/"` + JS 追加当前 version（见下"高保真项"） |
| `url_for('google_sheet.create')` / `(…, version=…)` | `/google-sheet/create` / `/google-sheet/create?version=cX` |
| `url_for('google_sheet.merge_export')` | `/google-sheet/merge-export` |
| `url_for('admin.dashboard')` | `/admin/` |
| `url_for('backtest_training.list_page' / 'create_page')` | `/backtest-training/list` / `/create` |
| `url_for('backtest_multi_product.list_page' / 'create_page')` | `/backtest-multi-product/list` / `/create` |
| `url_for('eastmoney_kline.index')` | `/eastmoney-kline` |

**高保真项**：`google_sheet/base.html:40` 导航"首页"链接带当前 version 参数（无 version 时省略）。静态化后由 `template-auth.js` 的导航处理逻辑补齐：`href` 写 `/google-sheet/`，页面加载时若 `URLSearchParams` 有 `version` 则 `a.href = '/google-sheet/?version=' + version`。行为与现在完全一致。

## 3. `{{ }}` 数据注入逐条替换

| # | 注入 | 位置 | 替换方案 |
|---|---|---|---|
| 1 | `{{ task_id }}`（href/展示，10 处） | backtest 双胞胎 detail/global_preview/result | URL 路径参数解析：`location.pathname.match(/\/detail\/([^/]+)/)[1]` 等（页面 JS 顶部原 `TASK_ID` 常量处） |
| 2 | `{{ task_id\|tojson }}` ×6 | 同上页面的 `<script>` 内 | 同 #1，`const TASK_ID = <运行时解析>` |
| 3 | `{{ result_id\|tojson }}` ×4、`{{ result_id }}` ×1 | backtest 双胞胎 result、export_preview | `/result\/(\d+)/` 路径解析 |
| 4 | `{{ version }}`（**JS 模板字符串内**，4 处） | google_sheet_c5/detail.html:2355,2370、c7/detail.html:2494,2509 | 页面 JS 顶部 `const CURRENT_VERSION = new URLSearchParams(location.search).get('version')`，原位置改用该常量（详见 §5） |
| 5 | `{{ next_url }}` | login.html:219 `<input hidden id="loginNextUrl">` | **保留 DOM 不动**，JS 初始化时 `document.getElementById('loginNextUrl').value = new URLSearchParams(location.search).get('next') \|\| ''`（该 input 的消费方 template-auth.js 不变） |
| 6 | `{{ 'true' if auth_enabled else 'false' }}` ×4 | admin/base、google_sheet/base、login、yule/sjxz 的 `<body>` | 直接删除该属性，见 §6 |
| 7 | `{{ google_sheet_table_type_options \| tojson }}` | admin/google_sheets.html:130 | `fetch('/api/meta/enums')` → `data.google_sheet_table_types`，在原位置以相同结构赋值给 `GOOGLE_SHEET_TABLE_TYPE_OPTIONS` |
| 8 | `{% for option in google_sheet_table_type_options %}` ×2 | admin/google_sheets.html:35,104 | 由 #7 的数据 JS 渲染 `<option>`，插入到原 `<select>` 位置；`selected` 判断沿用原 Jinja 分支逻辑 |
| 9 | `{% for option in task_status_options / task_type_filter_options / task_type_options / task_status_editable_options %}` ×4 | admin/tasks.html:161,170,248,467 | `fetch('/api/meta/enums')` → `task_statuses` / `task_types`（filter 用同一 `task_types`，editable 用 `task_status_editable`），同 #8 渲染 |

> #7~#9 的渲染函数放在对应 `pages/*.js`；`/api/meta/enums` 免登录、已有 6 处页面在用，是既有稳定契约（`meta_api.py:28`）。

## 4. 服务端页面逻辑前端化

### 4.1 `_resolve_task_version()` → dispatcher 页

**现状**：`/google-sheet/detail`（无 `version` 参数）与 `/google-sheet/create`（仅 `restart_task_id`）由服务端查库决定渲染哪个版本的模板（`google_sheet.py`）。

**静态化后**：新增两个轻量 dispatcher 页（唯一的"新 HTML"）：

- `templates/google_sheet/detail_dispatcher.html`
- `templates/google_sheet/create_dispatcher.html`

行为（两模式一致）：

```js
// 伪码，~30 行
const taskId = params.get('task_id');           // detail
const restartId = params.get('restart_task_id');// create
fetch('/api/tasks/' + (taskId || restartId))
  .then(r => r.json())
  .then(({ data }) => {
    const version = taskTypeToVersion(data.task_type); // 与原 _resolve_task_version 同一映射
    const sp = new URLSearchParams(location.search);
    sp.set('version', version);
    location.replace(location.pathname + '?' + sp.toString());
  });
```

- 有 `version` 参数时 nginx / Flask 直接返回对应版本文档，**不经过 dispatcher**；
- 仅缺 version 时才落入 dispatcher，多一次轻量请求 + 重定向（风险缓解：dispatcher 页带加载遮罩，样式沿用 `template-auth-loading`，无白屏闪烁）；
- 原映射关系以 `google_sheet.py` 现有 if 分支为准（c4/c5/c7/默认 C3、c31 仅 create），F2 时原文抄录为 `taskTypeToVersion()`。

### 4.2 导航版本高亮（google_sheet/base.html 的 `{% if current_version == … %}`）

导航条内联展开后，`active` class 与"当前模式"徽标由页面公共 JS 按 `URLSearchParams.get('version')` 计算（C3/C4/C5/C7/基础模式 五态 + 对应 badge 配色 class，原样迁移 Jinja 分支表）。实现放 `common/utils.js` 的 `initGoogleSheetNav()`，google_sheet 族各页在引入基座片段后调用。

### 4.3 backtest result 页的 task_id 推导

**现状**：`backtest_training.py:46`（multi_product 同形）服务端查 `TaskResult` → 所属 task 的 type 校验后注入 task_id。
**替换**：页面 JS 初始化本就要 fetch 结果数据（`/api/task-result/<id>`，已存在）；把 task_id 从该响应读取后再渲染"返回详情"链接（原 `{{ task_id }}` href 处）。**响应中无 task_id 时**（类型不匹配的降级分支，现服务端返回空串）按空串处理，行为一致。执行 F4 前先核对该接口响应字段，缺则该页改用 `/api/tasks/` 概要接口兜底——以实测为准，不预先加接口。

### 4.4 admin 枚举注入的删除

`admin.py:41`（tasks 页 4 个枚举参数）与 `admin.py:87`（google_sheets 页）的 `render_template` 上下文参数随路由改 `send_from_directory` 一并消失（`05` §2.2），前端走 §3 #7~#9。

## 5. JS 内嵌 Jinja 高危点清单（搬移时逐字核对）

| 文件:行 | 原文 | 处理 |
|---|---|---|
| google_sheet_c5/detail.html:2355 | `` `/google-sheet/create?version={{ version }}&restart_task_id=…` `` | `…?version=${CURRENT_VERSION}&restart_task_id=…` |
| google_sheet_c5/detail.html:2370 | `` `/google-sheet/detail?task_id=…&version={{ version }}` `` | 同上 |
| google_sheet_c7/detail.html:2494 | 同 c5:2355 | 同上 |
| google_sheet_c7/detail.html:2509 | 同 c5:2370 | 同上 |

其余页面内联 JS 无 Jinja 残留（已按 `grep -n "{{" templates/**/*.html` 全量核对，`{{ }}` 仅存在于上表与 §3 所列位置）。

## 6. `auth_enabled` 移除依据（决策 D3 细化）

- 服务端事实：`AUTH_ENABLED=false` 仅 development 允许，其他环境启动即拒绝（`app/utils/auth.py:16` `SAFE_AUTH_DISABLED_ENVS = {'development'}`、`auth.py:67` 启动校验）。**生产与测试环境该值恒为 true**；
- 客户端事实：`template-auth.js` `isAuthEnabled()` 实现为 `raw !== "false"`（`template-auth.js:83` 附近）——**属性缺失时返回 true**，即"鉴权开启"正是默认行为；
- 操作：4 处 `<body>` 的 `data-auth-enabled="{{…}}"` 属性整体删除，JS 零改动；
- 影响面：development 若用 `AUTH_ENABLED=false`，浏览器页面将走真实登录（此前是免登录直达）。服务端 mock 用户对 API 的放行逻辑不变，非浏览器场景（脚本/测试）完全不受影响。开发时可改用 `AUTH_ENABLED=true`（development 允许默认 JWT 密钥，启动校验放行）。

## 7. 完整性验收（每批必跑）

```bash
# 1) 已改造页面零 Jinja 残留（对当批文件）
grep -n "{{\|{%" templates/google_sheet/merge_export.html   # 期望无输出

# 2) 全库注入点未超出本清单（执行前重跑，若多于 §3/§5 所列，先补文档再动代码）
grep -rn "{{" templates --include="*.html" | grep -v url_for
```

## 8. 布局基座内联展开细则

| 基座 | 规模 | 展开规则 |
|---|---|---|
| `templates/admin/base.html`（482 行） | `<head>` 资源 4 行、导航+侧栏 ~350 行（含 11.6KB 内联 style）、`{% block head %}`(:353)、`{% block content %}`(:402)、共享脚本 3 段(:407-479)、`{% block scripts %}`(:480) | 各 admin 页 = 基座骨架逐字节复制 + 四个 block 位填入本页内容；侧栏脚本(:408-478)收敛为 `static/js/common/admin-shell.js` 引入；**展开后本族最后一页完成时删除 base.html** |
| `templates/google_sheet/base.html`（148 行） | `<head>` 资源 3 行、导航 100 行（含 version 分支）、工具脚本 28 行、`{% block %}` ×3 | 同上；工具脚本收敛进 `static/js/common/utils.js`（同名同签名）；version 高亮逻辑见 §4.2 |
| `templates/login.html` / yule / eastmoney_kline 等独立页 | 无基座 | 仅做 §3/§5 替换 |

展开是**机械复制**，禁止顺手"优化"任何标记/缩进/属性顺序——保证改造前后 `diff`（除已知替换点外）为空，截图对比才有意义。
