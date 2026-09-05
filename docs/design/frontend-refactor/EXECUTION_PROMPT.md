# 前端静态化重构 · 执行提示词（目标模式入口）

> 本文件是 `docs/design/frontend-refactor/` 六份设计文档的执行摘要，可直接整段复制给执行代理作为目标提示词。冲突裁决顺序：本提示词红线 > 六份文档 > 实际调用点代码。

---

你是在 `D:\Users\Administrator\Desktop\谷歌参数批量校验` 仓库（Flask 长时任务执行平台，dev_vue 分支）执行**前端静态化重构**的代理。完整设计已定稿于 `docs/design/frontend-refactor/`，共 6 份文档：

- `README.md` —— 背景、实测数据、目标/非目标、设计决策 D1~D8
- `01-frontend-inventory.md` —— 前端资产全量清点（模板/路由/注入点/CDN/存储键/重复度）
- `02-target-architecture.md` —— 目标目录结构、JS/CSS 分层规范、缓存策略
- `03-jinja-removal.md` —— Jinja 注入点全量清单与逐条替换方案（含服务端逻辑前端化）
- `04-execution-checklist.md` —— 批次 F0~F6、每页验证四件套、回滚
- `05-deployment.md` —— Flask `send_from_directory` 与 nginx 双部署

## 第 0 步（强制）

开工前通读上述 6 份文档；每批动手前重读 `03`（注入点对照）与 `04`（该批清单）。行号若有偏移以实际代码为准；文档与代码冲突时以实际代码为准，并把偏差登记到 `04` 文末"执行记录"表（首次执行时创建）。注意：仓库含大量中文，PowerShell 读写文件显式 UTF-8。

## 目标

1. `templates/` 45 个在用页面（F0 后）全部**零 Jinja 语法**：终验 `grep -rn "{{\|{%" templates --include="*.html"` 输出为空；
2. 全部内联 `<script>` 剪切到 `static/js/pages/<模板名>.js`（与页面一一对应），内联 `<style>` 剪切到 `static/css/pages/`；跨页重复工具收敛 `static/js/common/`（`utils.js`、`admin-shell.js`）；
3. 37 条页面路由全部改为 `send_page()`（新增 `app/routes/page_files.py`，`send_from_directory` 封装）：终验 `grep -rn "render_template" app/routes --include="*.py"` 输出为空；
4. 原 Jinja 版 `templates/` 在 F0 打包归档 `docs/design/frontend-refactor/archive/templates-jinja-source.zip`（D8）；
5. 同一产物支持双部署：Flask 模式（每批验收形态）+ nginx 模式（`05` §3 conf，落地为 `docs/design/frontend-refactor/nginx.conf.example`）。

## 红线（任何批次不得违反）

- **视觉与 DOM 零改动**：不改结构、class、id、属性顺序；除已知替换点外 HTML diff 必须为空；每页改造前后同 URL 截图对比；
- **URL 零变化**：37 条页面路由路径、query 参数、`/login?next=` 形态逐一保持；
- **脚本搬移纪律**：普通 `<script src>`（禁 defer/async/type=module），放在原内联位置；JS 原样剪切不改写、不"顺手优化"；`template-auth.js`/`trading-date.js` **不迁移路径**；
- **机械搬移原则**：localStorage 恢复、模板回填、restart 回填逻辑必须整体搬移，禁止重写；发现 `04` 未收录的 Jinja 注入点 → **先补 `03` 文档再动代码**；
- 鉴权：删除 `data-auth-enabled` 属性（4 处），`template-auth.js` 的 `isAuthEnabled()` 对缺失属性默认 true（依据 `app/utils/auth.py:16,67` + `static/js/template-auth.js`），**不改其函数逻辑**；
- 服务端逻辑前端化的三处契约（`03` §4）：`_resolve_task_version` → dispatcher 页（版本映射原文抄录）；backtest result 页 task_id → 从既有结果接口响应取；枚举 → 已有 `/api/meta/enums`（**不新增任何后端接口**）；
- 孤儿/vendor 删除前必须 grep 验证零引用（`04` §F0 命令），`static/eastmoney-kline/js/layui.js` 与根 `static/js/layui.js` 是两份文件，勿混删；
- 后端只允许改页面路由返回方式；API 蓝图、任务执行链、模型层零改动；
- 每批一个分支/每页一个 commit（`refactor(frontend): de-jinja <page>`），单页可独立 revert；**全量 pytest 通过才进下一批**。

## 关键契约速记

- 页面骨架：基座内联展开（D6），导航高亮/版本徽标由 JS 按 `URLSearchParams` 计算（`03` §4.2），active class 结果与 Jinja 版逐字节一致；
- URL 参数获取：task_id/result_id 路径正则解析，version/next 用 `URLSearchParams`；`{{ version }}` 在 JS 模板字符串内的 4 处高危点见 `03` §5（`CURRENT_VERSION` 常量）；
- dispatcher 页（仅 2 个新增 HTML）：带 `template-auth-loading` 遮罩，`fetch /api/tasks/<id>` → 补 `version=` → `location.replace`；有 version 参数时 nginx/Flask 直出对应文档，不经过 dispatcher；
- 缓存：HTML `no-cache`，`/static/**` 长缓存 + 发布时统一替换 `?v=<release>`；
- `common/utils.js` 函数与被收敛的复制粘贴版**同名同签名**（以 `google_sheet/base.html:117-145` 内联版为基准）。

## 执行顺序（每批详见 04 文档）

1. **F0**：zip 归档原版（命令在 04）→ 删 4 孤儿模板（grep 验证）→ vendor 冗余清理（逐项 grep + `*.map` 全删）→ 建 `static/{js,css}/{common,pages}` 骨架 → 新增 `common/utils.js`；
2. **F1 试点**：`google_sheet/merge_export.html`（526 行）完整走一遍流程 + 路由切 `send_page`，验证方法论后批量；
3. **F2**：google_sheet 基座族 index/create/detail/c31 + 2 个 dispatcher 页 + 基座删除；`/google-sheet/`、`/create`、`/detail` 路由改按 version 分发；
4. **F3**：c4/c5/c7 六大页（先 create 后 detail；c5/c7 detail 含 JS 内嵌 Jinja 高危点）；
5. **F4**：backtest 双胞胎 10 页 + global_preview（bt/multi **各自独立搬移禁止互相参考**；result 页 task_id 前端化前先核对响应字段）；
6. **F5**：admin 13 页（tasks/google_sheets 的 6 组 option 循环改 `/api/meta/enums` 渲染）+ xpl 3 + yule 2 + eastmoney_kline + login；`admin/base.html` 最后删除；
7. **F6**：终验 grep 双清零 → 删 `_resolve_task_version()` → `template-auth.js` 删 `data-auth-enabled` 读取分支 → AGENTS.md 前端章节更新 → nginx.conf.example 落地 → 双部署验收（`05` §8 清单）。

## 每页/每批完成动作（固定循环）

1. 视觉：改造前后同 URL 截图对比（含登录后状态）；
2. 功能：按 `04` §F1 功能清单勾选（localStorage 恢复/模板回填/restart 回填/轮询/401 跳转/权限导航）；
3. `python -m pytest tests/unit tests/integration` 全绿；
4. `grep -n "{{\|{%" <当批页面>` 无输出；
5. git commit；在 `04` 文末"执行记录"表登记：日期 / 批次·页面 / 结果 / 偏差说明。

## 新增验证资产

- `docs/design/frontend-refactor/nginx.conf.example`（F6 交付）；
- 每页截图基线目录 `docs/design/frontend-refactor/screenshots/<page>/before|after.png`（F1 试点建立约定）；
- 回滚兜底：`archive/templates-jinja-source.zip`（解包覆盖 + 路由还原 `render_template` 即回到 Jinja 版）。
