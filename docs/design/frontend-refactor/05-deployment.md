# 05 — 双模式部署（nginx 独立 / Flask 托管）

> 同一套产物（`templates/` 纯静态 HTML + `static/`），两种部署方式，切换只改部署配置，不改代码。页面 URL 在两种模式下**完全一致**（含 `/login`、`/admin/**`、query 参数路由），书签与 `template-auth.js` 的 `legacyPathMap` 不受影响。

## 1. 拓扑

```
                ┌─ 模式 A（nginx 独立部署，生产推荐）
浏览器 ──► nginx ─┤   /static/**、页面 HTML ──► 直接发文件（templates/ + static/）
                │   /api/**              ──► proxy_pass ──► Flask（纯 API）
                └─ 模式 B（Flask 单进程）
                    页面路由                ──► send_from_directory(templates/…)
                    /static/**             ──► Flask 静态目录（现状不变）
```

前端所有请求均为**同源相对路径**（`/api/*`、`/static/*`），token 在 localStorage 由 JS 主动附加——两种模式都**不需要 CORS**。

## 2. 模式 B：Flask 托管（先做，作为模式 A 的常驻兜底）

### 2.1 页面文件助手

新增 `app/routes/page_files.py`（约 15 行）：

```python
from pathlib import Path
from flask import send_from_directory

PAGES_DIR = Path(__file__).resolve().parent.parent / "templates"

def send_page(relpath: str):
    """返回静态页面文件；relpath 使用 '/' 分隔，如 'admin/tasks.html'"""
    return send_from_directory(PAGES_DIR, relpath)
```

`send_from_directory` 自带路径穿越防护（safe join），无需额外校验。

### 2.2 路由改造清单（37 条页面路由）

改造是机械的，示例：

```python
# 改造前
@admin_bp.route('/tasks')
def tasks():
    return render_template('admin/tasks.html',
        task_status_options=TaskStatus.choices(), ...)   # 枚举注入随 03 §4.4 移除

# 改造后
@admin_bp.route('/tasks')
def tasks():
    return send_page('admin/tasks.html')
```

逐条对应关系见 `01` §3 路由清单；三类特殊路由：

| 路由 | 改造后行为 |
|---|---|
| `/google-sheet/`、`/create`、`/detail` | 保留 version 分发 if 分支，仅把每个分支的 `render_template(...)` 换成 `send_page('google_sheet_c5/create.html')` 等（`05` §2.3） |
| `/backtest-training/result/<int:result_id>`（multi 同） | 删除查库推导 task_id 的逻辑（`03` §4.3 前端化），直接 `send_page(...)` |
| `/login` | `send_page('login.html')`（`next_url` 已前端化） |

### 2.3 version 分发与 dispatcher（两模式行为对齐）

| 请求形态 | 模式 B 行为 |
|---|---|
| `/google-sheet/create?version=c5` | python if 分支 → `send_page('google_sheet_c5/create.html')` |
| `/google-sheet/detail?version=c7&task_id=…` | 同上 → c7 detail 文档 |
| `/google-sheet/create?restart_task_id=…`（无 version） | `send_page('google_sheet/create_dispatcher.html')` → 前端查任务补 version 重定向（`03` §4.1） |
| `/google-sheet/detail?task_id=…`（无 version） | `send_page('google_sheet/detail_dispatcher.html')` |
| `/google-sheet/create`（无任何参数） | 直接 C3 文档（与现状一致，不经 dispatcher） |

`_resolve_task_version()` 查库逻辑在 F6 删除——两模式下"version 从哪来"统一为：**参数里有就用参数，没有就由 dispatcher 补**，单一执行路径。

### 2.4 不变项

- Flask 静态目录 `/static`（`app/__init__.py` 现状）；
- 全部 `/api/**` 蓝图（本次重构零改动）；
- 全局错误处理器：页面路由仍走 HTML 错误页（`send_from_directory` 404 天然如此），符合 `app/errors.py` 的 `/api` 判定约定。

## 3. 模式 A：nginx 独立部署

### 3.1 完整参考配置

```nginx
server {
    listen 80;
    server_name tasks.example.com;

    # ---- 静态资源（长期缓存）----
    location /static/ {
        alias /opt/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # ---- API 反代 Flask ----
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;          # 导出/预览类接口耗时较长
    }

    # ---- 旧版重定向路由（/backtest → /backtest-training 等 legacy_bp）----
    # 直接交还 Flask 处理（仅两条 redirect），或按需改为 nginx 301：
    location /backtest { proxy_pass http://127.0.0.1:5000; }

    # ---- 根路径页面 ----
    location = / { try_files /google_sheet/index.html =404; }
    location = /login { try_files /login.html =404; }

    # ---- google_sheet 版本分发（对应 05 §2.3 表）----
    location = /google-sheet/ { try_files /google_sheet/index.html =404; }

    location = /google-sheet/create {
        if ($arg_restart_task_id != "") { rewrite ^ /google_sheet/create_dispatcher.html last; }
        if ($arg_version = "c31") { rewrite ^ /google_sheet_c31/create.html last; }
        if ($arg_version = "c5")  { rewrite ^ /google_sheet_c5/create.html last; }
        if ($arg_version = "c7")  { rewrite ^ /google_sheet_c7/create.html last; }
        if ($arg_version = "c4")  { rewrite ^ /google_sheet_c4/create.html last; }
        rewrite ^ /google_sheet/create.html last;            # 默认 C3
    }

    location = /google-sheet/detail {
        if ($arg_version = "c5") { rewrite ^ /google_sheet_c5/detail.html last; }
        if ($arg_version = "c7") { rewrite ^ /google_sheet_c7/detail.html last; }
        if ($arg_version = "c4") { rewrite ^ /google_sheet_c4/detail.html last; }
        rewrite ^ /google_sheet/detail_dispatcher.html last; # 无 version → dispatcher
    }

    location = /google-sheet/merge-export { try_files /google_sheet/merge_export.html =404; }

    # ---- 路径参数页（task_id / result_id 在路径里）----
    location ~ ^/backtest-training/detail/        { try_files /backtest_training/detail.html =404; }
    location ~ ^/backtest-training/global-preview/ { try_files /backtest_training/global_preview.html =404; }
    location ~ ^/backtest-training/result/\d+/export-preview { try_files /backtest_training/result_export_preview.html =404; }
    location ~ ^/backtest-training/result/        { try_files /backtest_training/result.html =404; }
    # backtest-multi-product 五条同形，替换路径前缀即可

    # ---- 其余页面：无扩展名 URL → 同名 .html ----
    location / {
        root /opt/app/templates;
        try_files $uri $uri.html $uri/ =404;   # /admin/tasks → admin/tasks.html
    }
}

# 精确首页/入口补充：
#   location = /admin/          { try_files /admin/dashboard.html =404; }
#   location = /eastmoney-kline { try_files /eastmoney_kline/index.html =404; }
#   location = /xpl/            { try_files /xpl/index.html =404; }
#   location = /yule/           { try_files /yule/index.html =404; }
#   location = /yule/sjxz       { try_files /yule/sjxz.html =404; }
#   location = /xpl/v1 /xpl/v2  { try_files $uri.html =404; }
#   location = /global-preview /global-preview/single_product { try_files /global_preview/index.html =404; }
```

说明：

1. **HTML 不缓存**：`location /` 未加 expires，nginx 默认发 `Etag/Last-Modified`，浏览器协商缓存，发布即生效（与 `02` §5 一致；如需更强可 `add_header Cache-Control "no-cache"`）；
2. `if` 仅用于 `rewrite … last`（nginx 中该用法是安全的官方模式）；
3. `$uri.html` 映射覆盖 admin 13 页与 xpl 简单页，无需逐条罗列；
4. gzip 建议在 http 块对 `text/html application/javascript text/css` 开启（内联时代单文件 80KB+，静态化后该收益转移到 js 文件上，效果等同）。

### 3.2 nginx 模式的 Flask 角色

Flask 只跑 `/api/**`（含 auth）。**不需要**为模式 A 保留页面路由，但也不删除——同一份代码同时支持两种模式（无兼容层原则指"代码内无双轨"，双部署是部署形态选择）。

## 4. 环境矩阵

| 环境 | `AUTH_ENABLED` | 前端行为 | 说明 |
|---|---|---|---|
| production / testing | 必须 `true`（启动校验强制，`auth.py:67`） | 真实登录流程 | 前端已写死按"鉴权开启"运行，与服务端一致 |
| development | `true`（推荐） | 真实登录 | 允许默认 JWT 密钥 |
| development | `false` | 页面会要求登录（行为变化点，见 `03` §6）；服务端 API 对脚本/测试仍免鉴权（mock 用户） | 仅影响浏览器交互体验 |

| 配置 | 模式 A | 模式 B |
|---|---|---|
| `JWT_SECRET_KEY` | Flask 侧配置 | Flask 侧配置 |
| 页面目录 | nginx `root`/`alias` 指向 `/opt/app/templates` | 代码内 `PAGES_DIR`（相对仓库，无需配置） |

## 5. 缓存策略（两模式一致）

见 `02` §5。补充部署操作：**每次发布**将页面内 `common/`、`pages/`、`css/pages/` 引用的 `?v=` 统一替换为发布号（如 `?v=20260904_f2`）——可用一次性脚本或发布模板替换，漏改某页的后果仅是该页多取一次协商缓存，无正确性风险。

## 6. CDN 本地化（可选批次 P2，本次静态化不含）

内网/离线 nginx 部署时必须做；公网部署可选。清单与去向：

| CDN 库 | 引用页 | 去向 |
|---|---|---|
| chart.js（两个版本收敛为一） | admin/dashboard、backtest 双胞胎 result | `static/vendor/chart.umd.min.js` |
| xlsx-js-style 1.2.0 | backtest 双胞胎 result | `static/vendor/xlsx.bundle.js` |
| jquery（两个版本） | xpl 页 | `static/vendor/jquery-3.7.1.min.js`（择一版本，验证 xpl 兼容） |
| gsap + ScrollTrigger、swiper 11、tailwind JIT | yule/sjxz | tailwind JIT CDN **建议趁 P2 一并替换**为预编译 CSS（运行时编译器是生产隐患）；gsap/swiper 入 vendor |

## 7. 上线切换

1. 模式 B 全量完成后（F6），系统运行形态与今天完全一致——本身就是可上线状态；
2. 启用模式 A：部署 nginx，`/api/` 指向现有 Flask（零改动），灰度可按 `server_name` 或端口并行验证；
3. 模式 A 稳定后，Flask 可缩到仅 API 职责（页面路由保留不动，作为随时可切的兜底）。

## 8. 部署验收清单

- [ ] 模式 A 与模式 B 下，全部 37 个页面 URL 逐个访问 200 且截图一致
- [ ] `/login → 登录 → 回跳原页`（`next` 参数）两模式一致
- [ ] 无 version 的 `/google-sheet/detail?task_id=…` 经 dispatcher 正确落到对应版本文档
- [ ] `/static/**` 命中缓存头（模式 A `immutable`；二次访问 304/内存缓存）
- [ ] `/api/**` 401 → 前端刷新 token 重放 → 登录过期跳 `/login?next=…`（拦截链两模式一致）
- [ ] C31 批量创建 → 拆分子任务 → detail 跳转全链路
- [ ] 回测导出（xlsx-js-style CDN 未本地化时验证外网可达性）
