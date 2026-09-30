# 2026-09-30 GoogleSheet 页面族接入暗色主题

## 问题

`/google-sheet` 页面族的任务列表与创建页在暗色主题下整页无明暗变化（切换主题无效果，恒为浅色）：`/google-sheet/?version=c7` 等地址对应的页面只加载了 `static/css/common/base.css`（仅 6 行浅色样式），未加载暗色主题所需的 `static/css/common/theme.css`；而同族的 detail 页早已挂载 theme.css，明暗正常。

受影响页面（7 个）：

- `templates/google_sheet/index.html`（任务列表首页）
- `templates/google_sheet/create.html`（C3 创建）
- `templates/google_sheet_c31/create.html`、`google_sheet_c5/create.html`、`google_sheet_c7/create.html`、`google_sheet_c4/create.html`（各版本创建页）
- `templates/google_sheet/merge_export.html`（合并导出）

排查确认：以上页面均为纯 Bootstrap 类布局，无内联 `<style>`、无硬编码颜色（grep 验证为零），缺的只是 theme.css 这一个 link；navbar 为 `navbar-dark bg-primary` 蓝底横条，明暗通用，无需处理。

## 修复

1. **补挂 theme.css**：上述 7 个页面在 `base.css` 之后插入 `<link href="/static/css/common/theme.css" rel="stylesheet">`，与同族 detail 页（base.css + theme.css + components.css）链路对齐；components.css 是详情页专用组件（日志终端/C 系结果表等），列表与表单页不需要。
2. **theme.css 公共缺口补齐**（本次切换暗色后随即暴露的两处 Bootstrap 5.2 定值浅色）：
   - 分页 `.page-link` 系列（`--bs-pagination-bg:#fff` 等定值）：补暗色底 `#182132`、边框 `#334155`、hover/focus、active 蓝底 `#3b82f6`、disabled 灰显；
   - `.alert-warning`（`--bs-alert-bg:#fff3cd` 定值亮黄）：经 `--bs-alert-*` 变量改为降饱和暗琥珀（`rgba(245,158,11,.12)` 底 + `#fcd34d` 文字），与仓库"同色系半透明底 + 亮色文字"暗色惯例一致。

所有新增规则限定在 `html[data-bs-theme="dark"]` 作用域，浅色主题零变化。

## 验证

以与线上一致的 CSS 链路构造暗色复现页（任务列表页注入统计卡数字/状态徽章表格/分页/待重启警告框，C7 创建页渲染完整表单），无头 Chrome 截图经视觉验收通过：

- 列表页：4 张统计卡暗色可读、警告框暗琥珀非刺眼亮黄、状态徽章可辨认、分页无白色块（当前页蓝底白字/禁用项灰显）；
- C7 创建页：整页暗色，表单卡片/label/输入框/占位符全部清晰，无白色块残留与布局回归。

## 影响范围

- 7 个模板各加一行 CSS link + theme.css 公共暗色规则，无 Python/JS 改动，不影响任务创建/详情接口；
- 分页与 alert-warning 的暗色规则为全站公共生效（admin 等页面此前若存在同类白色分页块一并修复）。
