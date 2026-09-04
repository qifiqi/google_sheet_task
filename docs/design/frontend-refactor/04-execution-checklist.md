# 04 — 执行清单（批次 F0~F6）

> 每批一个 git 分支（`refactor/frontend-F<n>`），批内每页一个 commit（`refactor(frontend): de-jinja <page>`），保证**单页可独立 revert**。全批验收通过后合并 `dev_vue`。

## 0. 总则

**搬移纪律**（对应 AGENTS.md "不要做的事"）：

1. 内联 JS **原样剪切**到 `static/js/pages/<名>.js`，不改逻辑、不改顺序、不"顺手优化"；
2. `<script src>` 用普通脚本（无 defer/async/module），放在原内联位置（`02` §3.2）；
3. 每页改造必须同时覆盖：静态 HTML、抽离 JS、抽离 CSS、页面路由切换、该页 localStorage/回填功能验证；
4. 发现本文档未收录的 Jinja 注入点：**先补 `03` 再动代码**。

**每页验证四件套**：

| 项 | 方法 |
|---|---|
| 视觉零变化 | 改造前后同 URL 截图对比（浏览器 devtools 截全页，含登录后状态） |
| 功能零变化 | 页面功能清单（见 §F1 附表，按页勾选） |
| 回归 | `python -m pytest tests/unit tests/integration` 全绿 |
| 残留 | `grep -n "{{\|{%" <当批页面文件>` 无输出（`03` §7） |

---

## F0 准备批（0 页改造）

1. **zip 归档原版**（决策 D8）：
   ```bash
   # 仓库根目录（Git Bash）
   mkdir -p docs/design/frontend-refactor/archive
   zip -r docs/design/frontend-refactor/archive/templates-jinja-source.zip templates -x "*.pyc"
   # 或 PowerShell：
   # Compress-Archive -Path templates -DestinationPath docs/design/frontend-refactor/archive/templates-jinja-source.zip
   ```
   归档后 `unzip -l` 核对 49 个 html 齐全，然后**归档文件不参与任何运行时**。
2. **删孤儿模板**（先 grep 复核再删）：`templates/{base,index,index2,sjhp}.html`。
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
4. **建骨架**：`static/js/{common,pages}`、`static/css/{common,pages}`、归档目录，`.gitkeep` 占位。
5. **新增 `static/js/common/utils.js`**：以 `google_sheet/base.html:117-145` 内联脚本为基准搬运三个工具函数（同名同签名，此时尚无引用方，F2 起接入）。

**回滚**：整批 revert；zip 归档保留在批次 commit 中。

---

## F1 试点批：`google_sheet/merge_export.html`（1 页）

选它因为：526 行、无 `{{ }}` 数据注入（仅 1 处 `{% ` 相关 + url_for）、依赖 `google_sheet/base.html`——正好验证基座展开方法论。

步骤：

1. 截图留底（改造前）；
2. 复制 `google_sheet/base.html` 骨架内联展开到页首，替换其 `url_for`（`03` §2）；
3. `{% block content %}` 内容就位；删除 `{% extends %}/{% block %}`；
4. 内联 `<script>` 剪切 → `static/js/pages/google_sheet_merge_export.js`（普通 src，原位置）；
5. 内联 `<style>`（若有）→ `static/css/pages/google_sheet_merge_export.css`；
6. 基座工具函数改引 `common/utils.js`；
7. 路由切换（`05` §2.2）：`merge_export` → `send_from_directory`；
8. 验证四件套 → commit。

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
| `google_sheet/index.html` | 导航高亮由 §4.2 JS 接管；`{{request.args.get('version')}}`×2 在 JS 内（按 `03` §5 同法处理）；引用了 CDN bootstrap@5.1.3（保留外链不动，P2 再本地化） |
| `google_sheet/create.html`（C3） | `const TASK_ID` 类常量改为 `URLSearchParams` |
| `google_sheet/detail.html` | 同上 |
| `google_sheet_c31/create.html`（2506 行） | 纯机械搬移；提交后跑 C31 拆分子任务冒烟 |
| `google_sheet/create_dispatcher.html` | **新增**（`03` §4.1），含 `taskTypeToVersion()`（映射原文抄自 `google_sheet.py`） |
| `google_sheet/detail_dispatcher.html` | 同上 |
| 基座 `google_sheet/base.html` | 本批最后一页完成后：utils 收敛完成 → **删除基座文件** |

路由同步切换（`05` §2.2/§2.3）：`/`、`/create`、`/detail` 改为按 version 分发 + 无 version 落 dispatcher。

---

## F3 批：c4/c5/c7 六大页（6 页）

顺序：每版先 `create` 后 `detail`（create 相对独立，detail 含 §5 高危点）。

| 页面 | 行数 | 特殊点 |
|---|---|---|
| c4/create, c5/create, c7/create | 2335/2567/2801 | 机械搬移；`*_form_data` localStorage 恢复逐键验证 |
| c4/detail | 2510 | 机械搬移 |
| c5/detail, c7/detail | 2497/2636 | **JS 模板字符串内 `{{ version }}` ×4**（`03` §5），`CURRENT_VERSION` 常量就位后逐处替换 |

验证重点：restart 回填（detail → create 带 `restart_task_id` 跳转）、K 线自定义模式（custom）字段、取消任务按钮。

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
| 基座 `admin/base.html` | | admin 族全部完成后删除 |

---

## F6 收尾批（0 页改造）

1. 全库路由终检：37 条页面路由全部 `send_from_directory`，无 `render_template` 残留：
   ```bash
   grep -rn "render_template" app/routes --include="*.py"    # 期望无输出
   grep -rn "{{\|{%" templates --include="*.html"            # 期望无输出
   ```
2. 删除 `_resolve_task_version()`（已被 dispatcher 取代，`03` §4.1）；
3. `template-auth.js` 删除 `data-auth-enabled` 读取分支（此时 4 处注入属性已全部消失）；
4. AGENTS.md 更新：前端章节（目录约定、pages/common 分层、dispatcher、双部署入口指向本目录文档）；
5. 双部署验收（`05` §8 清单）；
6. 合并分支，zip 归档随仓库保留。

## 回滚策略

| 层级 | 操作 |
|---|---|
| 单页 | `git revert <该页 commit>`（每页独立 commit 的意义） |
| 批次 | 分支不合并即可；已合并则 revert merge commit |
| 整体 | `templates-jinja-source.zip` 是最终兜底（解包覆盖即回到 Jinja 版，配合 `render_template` 路由） |
