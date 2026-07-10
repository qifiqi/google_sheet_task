# Admin Web 当前代码与组件梳理

本文档配合 `docs/design/admin-web-ui-style-guide.md` 使用，用于约束当前 Vue admin web 的代码结构、组件边界和后续拆分方向。

## 1. 当前前端结构

```text
frontend/src
├─ api
│  └─ http.ts
├─ composables
│  ├─ useAuth.ts
│  └─ useNavigation.ts
├─ layout
│  ├─ AdminLayout.vue
│  ├─ AdminSidebar.vue
│  ├─ AdminTopbar.vue
│  └─ AppMenuItem.vue
├─ router
│  └─ index.ts
├─ types
│  └─ api.ts
├─ views
│  ├─ DashboardView.vue
│  └─ LoginView.vue
├─ App.vue
├─ main.ts
└─ style.css
```

## 2. 已有模块职责

| 文件 | 当前职责 | 规范状态 | 处理建议 |
| --- | --- | --- | --- |
| `main.ts` | 注册 Vue、Vue Router、Element Plus、全局样式 | 符合 | 保持入口精简 |
| `App.vue` | Element Plus 全局配置和路由出口 | 符合 | 保持只做 provider，不放业务 UI |
| `style.css` | 全局后台 token、reset、Element Plus 基础覆盖 | 已整理 | 后续颜色/尺寸优先从这里取 |
| `router/index.ts` | `/web/` 路由、登录守卫、鉴权加载 | 符合 | 新增页面时继续挂在 `AdminLayout` children 下 |
| `api/http.ts` | token 存储、请求封装、401 refresh 重试 | 符合 | 不在组件内重复写 fetch 鉴权逻辑 |
| `useAuth.ts` | 登录、退出、当前用户、权限判断 | 符合 | 继续作为鉴权唯一前端状态源 |
| `useNavigation.ts` | 加载 `/api/meta/nav`，生成侧边栏叶子节点 | 符合 | 菜单权限继续以后端返回为准 |
| `AdminLayout.vue` | 后台壳：侧栏、顶栏、标签栏、内容区 | 基本符合 | 后续把标签栏可抽成 `AdminTabs.vue` |
| `AdminSidebar.vue` | 品牌区、权限菜单、折叠态 | 基本符合 | 后续接入生成 logo 图片 |
| `AdminTopbar.vue` | 折叠按钮、搜索、工具图标、用户下拉 | 基本符合 | 刷新/搜索可在后续接真实交互 |
| `AppMenuItem.vue` | 递归渲染菜单项和子菜单 | 符合 | 图标映射保持集中维护 |
| `LoginView.vue` | 登录页表单和鉴权提交 | 基本符合 | 后续接入背景图、logo、登录图 |
| `DashboardView.vue` | 仪表盘请求、KPI、图表、表格、活动列表 | 需要拆分 | 下一阶段按下方组件图拆 |

## 3. 现有代码已对齐的规范

| 规范项 | 当前落点 |
| --- | --- |
| 当前鉴权 | `useAuth.ts` + `router/index.ts` |
| 当前侧边栏权限 | `useNavigation.ts` + `/api/meta/nav` |
| Element Plus 2.10+ | `main.ts` 全局注册 |
| 浅色后台基调 | `style.css` token |
| 侧边栏布局 | `AdminSidebar.vue` |
| 顶部栏布局 | `AdminTopbar.vue` |
| 表格基础样式 | `style.css` 对 `ElTable` 的统一覆盖 |
| 按钮/标签基础圆角 | `style.css` 对 `ElButton` / `ElTag` 的统一覆盖 |

## 4. 当前主要问题

| 优先级 | 问题 | 影响 | 处理方式 |
| --- | --- | --- | --- |
| P0 | `DashboardView.vue` 同时承担数据请求和多块 UI 展示 | 后续任务面板、图表、表格扩展会变难 | 拆成 dashboard feature 组件 |
| P0 | 生成素材还未接入项目目录 | 登录页、Logo、背景图仍是 CSS 占位 | 选定最终素材后放入 `frontend/src/assets/generated` |
| P1 | 部分页面色值仍在局部组件中 | 主题调整成本高 | 逐步替换为 `style.css` token |
| P1 | 标签栏在 `AdminLayout.vue` 内部 | 页面壳职责略重 | 抽成 `AdminTabs.vue` |
| P1 | 顶栏搜索、刷新、通知是静态按钮 | 交互还未完整 | 接入当前路由刷新、搜索弹层、消息状态 |
| P2 | `frontend/src/assets` 仍保留 Vite 示例素材 | 容易混淆项目资产 | 接入生成素材后删除未使用示例资源 |

## 5. 建议组件拆分图

下一阶段实现后台页面时，优先按 feature 目录组织：

```text
frontend/src
├─ components
│  ├─ admin
│  │  ├─ AdminCard.vue
│  │  ├─ AdminStatusTag.vue
│  │  ├─ AdminPageHeader.vue
│  │  └─ AdminTableActions.vue
│  └─ dashboard
│     ├─ DashboardMetricGrid.vue
│     ├─ DashboardMetricCard.vue
│     ├─ DashboardTrendCard.vue
│     ├─ DashboardCompletionCard.vue
│     ├─ DashboardRecentTasks.vue
│     ├─ DashboardActiveTasks.vue
│     └─ DashboardMiniStats.vue
├─ composables
│  ├─ useAuth.ts
│  ├─ useNavigation.ts
│  └─ useDashboardOverview.ts
└─ views
   ├─ DashboardView.vue
   └─ LoginView.vue
```

## 6. 组件职责定义

| 组件 | 职责 | Props | Emits |
| --- | --- | --- | --- |
| `AdminCard` | 统一卡片头部、内边距、右侧操作 | `title`, `subtitle` | 无 |
| `AdminStatusTag` | 根据业务状态输出统一文案和颜色 | `status` | 无 |
| `AdminPageHeader` | 页面标题、面包屑、主操作区 | `title`, `subtitle` | 按操作透传 |
| `AdminTableActions` | 表格操作列统一布局 | `actions` | `action` |
| `DashboardMetricGrid` | 组合 KPI 卡片 | `cards` | 无 |
| `DashboardMetricCard` | 单个 KPI 指标展示 | `card` | 无 |
| `DashboardTrendCard` | 任务趋势图表 | `trendItems` | `refresh` |
| `DashboardCompletionCard` | 完成率环形进度 | `summary` | 无 |
| `DashboardRecentTasks` | 最近任务表格 | `tasks`, `checkedAt` | `view` |
| `DashboardActiveTasks` | 运行中任务列表 | `tasks` | `view` |
| `DashboardMiniStats` | 底部小统计卡片 | `summary`, `trendCount` | 无 |

`DashboardView.vue` 后续只保留页面编排：

```text
DashboardView
├─ useDashboardOverview()
├─ DashboardMetricGrid
├─ DashboardTrendCard
├─ DashboardCompletionCard
├─ DashboardRecentTasks
├─ DashboardActiveTasks
└─ DashboardMiniStats
```

## 7. 数据与状态规则

| 状态 | 规则 |
| --- | --- |
| 鉴权状态 | 只能从 `useAuth()` 读取和修改 |
| 菜单状态 | 只能从 `useNavigation()` 读取 |
| 请求 loading | 在 feature composable 内维护，view 只消费 |
| 接口错误 | composable 暴露 `loadError`，view 决定如何展示 |
| 派生数据 | 用 `computed`，不要在 template 中直接 filter/sort/map 复杂数据 |
| 表格状态 | 分页、筛选、排序后续放到对应 feature composable |

## 8. 后续代码约束

1. 新增页面时先查 `admin-web-ui-style-guide.md`，再写组件。
2. 页面级 `views/*.vue` 只做数据组合和布局，不堆大量展示细节。
3. 超过 3 个独立 UI 区块的 view 必须拆 feature components。
4. 可复用状态标签、卡片、表格操作列优先放 `components/admin`。
5. 与业务接口绑定的页面逻辑优先放 `composables/useXxx.ts`。
6. 不在组件里重复定义主色、圆角、表格行高等全局规范值。
7. 不硬编码完整侧边栏菜单，必须依赖 `/api/meta/nav`。

## 9. 下一步落地顺序

1. 接入 A 风格对应的 logo、背景图、登录图到 `frontend/src/assets/generated`。
2. 新增 `components/admin` 基础组件：状态标签、卡片、表格操作。
3. 新增 `useDashboardOverview.ts`，从 `DashboardView.vue` 移出请求和派生数据。
4. 拆分 `DashboardView.vue` 的 KPI、趋势、表格、活动列表。
5. 根据真实后端数据补齐任务列表页、资源页、日志页。
6. 每阶段完成后运行 `npm run build` 验证 TypeScript 与 Vue SFC。
