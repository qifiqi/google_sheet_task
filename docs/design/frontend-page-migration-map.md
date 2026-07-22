# Vue 页面迁移目录与路由地图

本文档规定旧 Flask/Jinja 模板迁移到 Vue 的页面放置方式。视觉与交互仍以 `docs/design/admin-web-ui-style-guide.md` 为准。

## 目录规则

```text
frontend/src/
├─ pages/                    # 仅路由页面，按业务域归档
│  ├─ auth/                  # 登录等公开页面
│  ├─ dashboard/             # 管理后台工作台
│  ├─ tasks/                 # 任务、模板、结果、XPL 运维
│  ├─ data/                  # 汇总、分析等数据看板
│  ├─ scheduler/             # 定时任务
│  ├─ analysis/              # V1 分析、回测结果与全局预览的共享页面
│  ├─ system/                # 配置、资源、RBAC、日志、导航
│  ├─ google-sheet/          # C3/C31/C4/C5/C7 任务流
│  ├─ backtest-training/     # 单品回测流程
│  ├─ backtest-multi-product/# 多品回测流程
│  ├─ xpl/                   # 夏普率与分析流程
│  ├─ yule/                  # 独立业务工具
│  └─ shared/                # 仅页面层共用的轻量组件
├─ components/<domain>/      # 可复用展示组件，props down / events up
├─ composables/              # 可复用请求、状态与副作用
├─ utils/                    # 纯函数
├─ styles/<domain>/          # 页面或领域的独立 CSS 小文件
└─ router/                   # 路由与旧路径映射
```

- 新页面只能进入 `pages/<domain>/`，不再新增扁平 `src/views/` 文件。
- 页面只负责编排页面组件与 composable；表格、筛选、编辑器、详情抽屉等独立区域放入 `components/<domain>/`。
- 页面 CSS 必须位于 `styles/<domain>/`，不使用 `style` 属性，也不在单个 CSS 文件堆积多个页面规则。
- `router/migration-pages.ts` 是旧导航路径到 Vue 路径的唯一映射，`AdminLayout` 不再维护第二份分散映射。

## 已迁移页面

| Vue 页面 | 旧模板 | Vue 路由 |
| --- | --- | --- |
| `pages/dashboard/DashboardView.vue` | `templates/admin/dashboard.html` | `/` |
| `pages/tasks/TaskListView.vue` | `templates/admin/tasks.html` | `/tasks` |
| `pages/tasks/TemplateListView.vue` | `templates/admin/templates.html` | `/templates` |
| `pages/tasks/ResultListView.vue` | `templates/admin/results.html` | `/results` |
| `pages/tasks/XplJobListView.vue` | `templates/admin/xpl_analysis_jobs.html` | `/xpl-analysis-jobs` |
| `pages/data/ModelSummaryView.vue` | `templates/admin/model_summary.html` | `/model-summary` |
| `pages/scheduler/SchedulerView.vue` | `templates/admin/scheduler.html` | `/scheduler` |

## 已创建的迁移占位页

| 旧模板组 | Vue 目录 | Vue 路由前缀 |
| --- | --- | --- |
| `templates/admin/{config,google_sheets,navigation,logs,users,roles}.html` | `pages/system/` | `/system/` |
| `templates/google_sheet*/{index,create,detail}.html` 与 `merge_export.html` | `pages/google-sheet/` | `/google-sheet/` |
| `templates/backtest_training/*` | `pages/backtest-training/` | `/backtest/training/` |
| `templates/backtest_multi_product/*` | `pages/backtest-multi-product/` | `/backtest/multi-product/` |
| `templates/xpl/{index,v1}.html` | `pages/xpl/` | `/xpl/` |
| `templates/yule/{index,sjxz}.html` | `pages/yule/` | `/yule/` |

每个占位页都有独立 `.vue` 文件，并复用 `pages/shared/LegacyPagePlaceholder.vue`。占位页提供旧 Flask 页面回退入口，迁移期间不影响已上线操作。

## 已合并的分析页面

`pages/analysis/AnalysisResultView.vue` 统一承接 XPL V1、单品回测结果和多品回测结果。来源差异由 `useAnalysisResult.ts` 适配，指标卡、趋势图、明细标签和导出操作不再复制三套实现。

`pages/analysis/GlobalPreviewView.vue` 统一承接单品和多品全局预览；多品比例计算与保存仅通过 `MultiProductRatioPanel.vue` 在多品来源下显示。

## 不生成路由的模板

下列文件是布局、局部片段或非 SPA 入口，不应一比一创建 Vue 页面：

- `templates/base.html`
- `templates/admin/base.html`
- `templates/google_sheet/base.html`
- `templates/admin/components/pagination.html`
- `templates/index.html`、`templates/index2.html`、`templates/sjhp.html`

它们的布局职责分别由 `App.vue`、`AdminLayout.vue`、页面级组件与路由承担。若后续确实需要将首页改造成 Vue 入口，应另建 `pages/home/`，不复用管理后台页面目录。

## 单页迁移顺序

1. 读取旧模板的静态表单、动态 DOM 初始化、localStorage 回填和提交 payload。
2. 保留占位页文件和路由名称，在同一路径内替换为真实页面实现。
3. 将数据请求和异步状态抽入 `use<Feature>.ts`，将表格、筛选、编辑表单拆为领域组件。
4. 将样式写入 `styles/<domain>/` 的小文件，只使用设计规范 token。
5. 保留旧页面回退直到真实 Vue 页面完成接口、权限、桌面与移动端验收。
