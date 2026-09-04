# 前端静态化重构方案（总览）

> 状态：方案已定稿，待执行。执行必须严格遵循本目录下各分册文档：
>
> - `README.md` —— 背景、实测数据、目标/非目标、核心设计决策（本文件）
> - `01-frontend-inventory.md` —— 前端资产全量清点（模板/路由/静态资源/CDN/存储键/重复度，全部带实测数据）
> - `02-target-architecture.md` —— 目标架构与规范（目录结构、JS/CSS 分层规范、缓存策略）
> - `03-jinja-removal.md` —— 模板语法移除对照（注入点全量清单 + 逐条替换方案）
> - `04-execution-checklist.md` —— 执行清单（批次 F0~F6、步骤、验证命令、回滚方式）
> - `05-deployment.md` —— 双模式部署（nginx 独立部署 / Flask `send_from_directory`）
> - `EXECUTION_PROMPT.md` —— 执行提示词（目标模式入口，可整段复制给执行代理）

## 1. 背景与动机

当前前端是"单页自包含 HTML"模式：49 个 Jinja 模板、共 55,779 行 / 2318 KB，其中**内联 `<script>` 占 1541 KB（约 66%）**，`static/` 下几乎没有项目自身的 JS/CSS（仅 `template-auth.js` 29KB、`trading-date.js` 1.4KB、`template-auth.css` 3KB，其余全是第三方库原始发行版）。

目标形态：**全部页面变成零 Jinja 语法的纯静态 HTML + 抽离的页面级 JS/CSS**，同一套产物支持两种部署：

1. **nginx 直接静态托管**（前端与 `/api` 反代分离，生产推荐）；
2. **Flask `send_from_directory` 返回**（单进程简单部署，行为与今天完全一致）。

与数据层重构（`docs/design/data-layer-refactor/`）相同的原则：**无兼容层、无双轨、单一执行路径**；且全程**不新增后端业务接口**（唯一动到的后端是 37 个页面路由的返回方式）。

## 2. 实测核心数据（2026-09-04 全量扫描）

| 指标 | 数值 | 证据 |
|---|---|---|
| 模板总数 | 49 个（含 4 个孤儿） | `find templates -name "*.html"` |
| HTML 总量 | 2318 KB / 55,779 行 | 逐文件统计 |
| 内联 `<script>` 总量 | 1541 KB（最大单页 84KB） | 正则提取逐文件统计 |
| 内联 `<style>` 总量 | 148 KB | 同上 |
| 项目自身静态 JS | 2 个文件（30.4 KB） | `static/js/` |
| 项目自身静态 CSS | 1 个文件（3.1 KB） | `static/css/template-auth.css` |
| 第三方库静态资源 | ~1608 KB JS + 全量 Bootstrap 变体 | `static/js`、`static/css` |
| 页面路由 | 37 条（9 个页面型蓝图） | `grep render_template app/routes` |
| Jinja 数据注入点 | 15 类 / 约 60 处，全部可枚举 | `01-frontend-inventory.md` §5 |
| CDN 外链依赖 | 11 个页面引用 9 种 CDN 库 | `01-frontend-inventory.md` §6 |
| 页面间重复度 | c5/c7 create 页函数集合相似度 91%；backtest 双胞胎 list/result 92% | 函数名 Jaccard 实测 |

**关键定性结论：服务端耦合度极低。** 页面数据全部来自 `/api/*` 同源 fetch；鉴权已完全客户端化（`template-auth.js` 拦截 fetch + localStorage JWT）；模板语法 90% 只是 `{% extends %}/{% block %}` 布局继承。真正的问题不是耦合，而是**没有分层**：JS 全部内联、零共享模块、大量复制粘贴。

## 3. 目标 / 非目标

### 目标

1. 前端继续使用 `templates/` 目录（**目录名与子目录形状不变**），全部文件零 Jinja 语法；原 Jinja 版本在 F0 整体打包 zip 留档（D8）；
2. 内联 JS 机械抽离到 `static/js/pages/*.js`，共享工具收敛到 `static/js/common/`；
3. URL、DOM 结构、class、视觉样式、功能点**零变化**；
4. 同一产物支持 nginx 独立部署与 Flask 托管，切换只改部署配置，不改代码；
5. 清理 4 个孤儿模板与 Bootstrap 冗余变体（grep 验证无引用后删除）。

### 非目标

1. **不引入 Vue/React/任何框架，不引入构建链**（webpack/vite）——用户明确不要 Vue；
2. 不改任何 API 行为、不新增业务接口；
3. 不做 CDN 库本地化以外的功能增强（CDN 本地化为可选 P2 批次）；
4. 不合并 c4/c5/c7、backtest 双胞胎等高相似页面（重复度治理另行立项，本次只做"搬移不重构"）。

## 4. 核心设计决策

| # | 决策 | 依据 |
|---|---|---|
| D1 | **零 Jinja**：所有 `{{ }}`/`{% %}` 移除，注入点用 query/path 参数解析或已有 API 替代 | 注入点仅 15 类，全部有对应替代（`03` 逐条对照） |
| D2 | **无构建、普通 `<script src>`**：抽离的 JS 保持非 module、不加 `defer`，放在原内联位置 | 内联脚本是按文档顺序同步执行的，改 module/defer 会改变初始化时序，是本次唯一高危点（`02` §3.2） |
| D3 | **鉴权标志前端写死为开启**：删除 `data-auth-enabled` 属性，`isAuthEnabled()` 属性缺失时天然返回 true | `AUTH_ENABLED=false` 被 `app/utils/auth.py:16,67` 启动校验限制为仅 development；生产永远为 true，无需传给前端 |
| D4 | **枚举注入改走已有 `/api/meta/enums`**：admin 页 6 处 `<option>` Jinja 循环改前端渲染 | 该接口已存在且已返回全部所需枚举（`app/routes/meta_api.py:28`），零后端改动 |
| D5 | **query 参数版本路由**（`/google-sheet/create?version=c5` 等按参数返回不同文档）：nginx 用 `$arg_version` rewrite 映射；Flask 模式保留现有 python 分发（改为按版本 `send_from_directory`）；无 version 的 `/detail` 由 dispatcher 页 fetch 任务后重定向补参 | 详见 `05` §2.3 / §3.2 |
| D6 | **布局基座内联展开**：每页成为完整 HTML，导航条标记接受重复（主动态本来就由 `template-auth.js` 接管） | 三套基座共 754 行，JS 共享部分只有 ~120 行；引 layout.js 动态注入 DOM 会改变首屏渲染路径，违背"样式零改动" |
| D7 | **孤儿与冗余清理**：删 `templates/{base,index,index2,sjhp}.html`；删 Bootstrap rtl/esm/map 等未引用变体 | 4 孤儿模板全库无 `render_template` 引用（已 grep 验证） |
| D8 | **`templates/` 目录名保留**：页面就地静态化，不做 `frontend/` 迁移；F0 先将原 Jinja 版 `templates/` 全量打包 `docs/design/frontend-refactor/archive/templates-jinja-source.zip` 留档 | 用户决策（2026-09-04）；避免 45 文件 `git mv` 噪音；Flask 与 nginx 均可直接指向该目录 |

## 5. 批次索引（详见 `04-execution-checklist.md`）

| 批次 | 范围 | 页数 | 风险 |
|---|---|---|---|
| F0 | 原 Jinja 版 `templates/` 打包 zip 归档、孤儿/冗余清理、`common/` 骨架 | 0 页改造 | 低 |
| F1 | 试点：`google_sheet/merge_export.html`（526 行，最小完整页） | 1 | 低（验证方法论） |
| F2 | google_sheet 基座族：base + index + create + detail + c31 | 6 | 中（含 dispatcher） |
| F3 | c4/c5/c7 create + detail（6 个最大页，2510~2801 行） | 6 | 中高（JS 内嵌 Jinja 在此） |
| F4 | backtest 双胞胎 10 页 + global_preview | 11 | 中（result 页 task_id 推导前端化） |
| F5 | admin 13 页 + xpl 3 页 + yule 2 页 + eastmoney_kline + login | 20 | 低（多为简单页） |
| F6 | 收尾：全部页面路由切 `send_from_directory`、AGENTS.md 更新、双部署验收 | 0 | 低 |

每批完成标准：该批页面在 **Flask 模式**下截图与改造前一致 + 功能清单通过 + `python -m pytest tests/unit tests/integration` 全绿。批次内页面可独立回滚（git revert 单页）。

## 6. 风险摘要

1. **脚本执行时序**（最高风险）：内联脚本同步按序执行；抽离时必须保持 `普通 <script src>` 原位置，禁止 module/defer。逐页验证 DOMContentLoaded 前后的初始化依赖。
2. **JS 内嵌 Jinja**：`google_sheet_c5/c7/detail.html` 的模板字符串里嵌着 `?version={{ version }}`，搬移时必须替换为运行时解析，此类点已逐条列入 `03` §5。
3. **dispatcher 页首屏闪动**：无 version 的 detail/create 会先渲染 dispatcher 再重定向，视觉上多一次跳转（与现状"服务端直接返回正确版本"不同），可接受，`05` §2.3 给了缓解措施。
4. **重复劳动量大**：45 页逐一搬移，靠批次化 + 每批固定验证清单控制质量。
