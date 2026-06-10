# Vue 前端重构计划 — 旧模板迁移至 Vue 3 SPA

## Context

当前项目 `templates/` 目录下有 38 个 Jinja2 模板（~47,000 行），构成完整的量化交易任务管理平台前端。`frontend/` 目录已搭建好 Vue 3 基础设施（API 层 13 个模块、路由守卫、7 个 composables、16 个共享组件），但 **所有页面视图（~33 个 Vue 文件）、主布局、全局样式** 尚未创建，当前无法运行。

本次目标：将旧模板完整迁移至 Vue 前端，保持功能布局不变，组件化、全局化，确保权限/登录流畅、动画平滑、构建后不白屏。

## 设计规范

- **UI 框架**：Element Plus（唯一）+ 已有共享组件，移除 Naive UI 依赖及相关文件
- **样式系统**：SCSS + CSS 变量主题（light/dark），通过 `data-theme` 属性切换
- **组件规范**：`<script setup>` + Composition API，View 作为组合层，逻辑下沉 composables
- **权限体系**：路由守卫（`meta.permission`）+ `v-permission` 指令，保持与旧版一致的权限码

---

## Task 0: 全局样式系统（前置依赖）

创建 3 个样式文件，建立设计基础。

### 文件清单

| 文件 | 内容 |
|------|------|
| `src/styles/_variables.scss` | CSS 变量定义（颜色、间距、圆角、阴影、字体），light/dark 双套变量 |
| `src/styles/_mixins.scss` | 响应式断点 mixin、暗色模式选择器、卡片/表格/表单通用 mixin |
| `src/styles/index.scss` | 全局重置、Element Plus 主题覆盖、工具类、过渡动画 |

### 关键设计
- 主色调：沿用旧版 admin/base.html 配色（light: `#f5f7fa`, dark: `#111827`）
- Element Plus 暗色模式已通过 `element-plus/theme-chalk/dark/css-vars.css` 导入
- 主题切换通过 `useTheme()` 设置 `document.documentElement.dataset.theme` + `.dark` class

### Naive UI 移除
- 从 `main.js` 移除 `naive-ui` 导入和 `.use(naive)`
- 删除 `src/components/naive/` 目录（5 个冗余组件）
- 从 `package.json` 移除 `naive-ui` 和 `@vicons/ionicons5` 依赖
- 确认无其他文件引用 naive-ui（已检查，所有 API 层和 composables 不依赖）

---

## Task 1: 主布局 + 登录页 + 403 页

### 文件清单

| 文件 | 对应旧模板 | 说明 |
|------|-----------|------|
| `src/layout/AppLayout.vue` | `admin/base.html` | 侧边栏 + 顶部栏 + 主内容区 |
| `src/layout/components/SidebarMenu.vue` | admin 侧边栏 | 递归菜单渲染，支持分组折叠 |
| `src/layout/components/SidebarMenuItem.vue` | 菜单项 | 单个菜单项/子菜单组 |
| `src/layout/components/AppHeader.vue` | admin 顶部栏 | 面包屑 + 用户头像下拉 + 主题切换 |
| `src/views/Login.vue` | `login.html` | 登录表单 + 主题切换 |
| `src/views/Forbidden.vue` | 无 | 403 无权限页面 |

### AppLayout 组件分解
```
AppLayout.vue（组合层）
├── SidebarMenu.vue → 使用 useNavigation() 获取菜单树
│   └── SidebarMenuItem.vue → 递归渲染，支持 icon + children
├── AppHeader.vue → 面包屑 + 用户信息 + el-switch(主题)
└── <router-view> → 页面内容区（带 Transition 动画）
```

### 关键集成点
- `useNavigation().ensureNavLoaded()` → 菜单数据（含旧路径映射）
- `useAuth()` → 用户信息、退出登录
- `useTheme().switchValue` → 暗色主题开关
- `useResponsive()` → 移动端侧边栏变为抽屉
- `v-permission` → 菜单项权限过滤
- 侧边栏折叠状态持久化到 localStorage（与旧版一致）

### 路由修正
- 将 `/403` 路由的 component 从 `Login.vue` 改为 `Forbidden.vue`

---

## Task 2: 任务管理模块（核心业务）

### 文件清单

| 文件 | 对应旧模板 | 说明 |
|------|-----------|------|
| `src/views/task/List.vue` | `google_sheet/index.html` | 任务列表 + 筛选 + 分页 |
| `src/views/task/Create.vue` | `google_sheet/create.html` | 通用创建表单（C3 基础版） |
| `src/views/task/CreateC3.vue` | `google_sheet/create.html` | C3 版本包装 |
| `src/views/task/CreateC4.vue` | `google_sheet_c4/create.html` | C4 版本包装 |
| `src/views/task/CreateC5.vue` | `google_sheet_c5/create.html` | C5 版本包装 |
| `src/views/task/CreateC31.vue` | `google_sheet_c31/create.html` | C31 批量创建包装 |
| `src/views/task/Detail.vue` | `google_sheet/detail.html`, C4/C5 detail | 任务详情（日志+结果+操作） |

### 组件分解

**List.vue**
```
List.vue
├── PageToolbar（已有）
├── StatCardGrid（已有）— 统计卡片
├── FilterToolbar（已有）— 状态/类型/搜索
└── DataTableCard（已有）
    ├── StatusTag（已有）
    ├── TaskProgressCell（已有）
    └── TaskActions.vue（新建）— 操作按钮组
```

**Create 系列**
```
CreateC3.vue / CreateC4.vue / CreateC5.vue / CreateC31.vue（薄包装层）
└── TaskFormCore.vue（共享表单核心）
    ├── TemplateSelector.vue — 模板选择下拉
    ├── GoogleSheetPicker.vue — Sheet URL + 工作表选择
    ├── TokenConfig.vue — Token 配置（文件路径/JSON 切换）
    └── ParameterGrid.vue — 动态参数组表格
```

**Detail.vue**
```
Detail.vue
├── PageToolbar（已有）
├── StatCardGrid（已有）— 任务状态统计
├── el-tabs
│   ├── TaskLogTab.vue → LogViewer（已有）+ usePolling 自动刷新
│   ├── TaskResultTab.vue → DataTableCard（已有）
│   └── TaskConfigTab.vue → CodeBlock（已有）展示 JSON 配置
└── TaskActions.vue — 停止/重启/删除
```

### 新增 Composables

| 文件 | 职责 |
|------|------|
| `src/composables/useTaskForm.js` | 表单状态管理、校验、提交 |
| `src/composables/useGoogleSheetPicker.js` | Sheet 列表加载、选择、刷新 |
| `src/composables/useParameterGrid.js` | 动态参数行增删、校验 |

---

## Task 3: 回测训练模块

### 文件清单

| 文件 | 对应旧模板 | 说明 |
|------|-----------|------|
| `src/views/backtest/List.vue` | `backtest_training/list.html` | 回测任务列表 |
| `src/views/backtest/Create.vue` | `backtest_training/create.html` | 创建回测（股票搜索+参数） |
| `src/views/backtest/Detail.vue` | `backtest_training/detail.html` | 回测详情 |
| `src/views/backtest/Result.vue` | `backtest_training/result.html` | 回测结果展示 |
| `src/views/backtest/GlobalPreview.vue` | `backtest_training/global_preview.html` | 全局预览 |

### 组件分解
```
Create.vue
├── StockSearch.vue — 股票搜索（el-autocomplete）
├── MarketSelector.vue — 市场选择（A股/美股）
├── BacktestParamForm.vue — 参数配置（年份、资金等）
└── el-upload — Excel 导入
```

### 新增 Composable
| 文件 | 职责 |
|------|------|
| `src/composables/useStockSearch.js` | 股票搜索防抖、结果缓存 |

---

## Task 4: 多产品回测模块

与 Task 3 结构对称，复用组件模式。

### 文件清单

| 文件 |
|------|
| `src/views/backtest-multi/List.vue` |
| `src/views/backtest-multi/Create.vue` |
| `src/views/backtest-multi/Detail.vue` |
| `src/views/backtest-multi/Result.vue` |
| `src/views/backtest-multi/GlobalPreview.vue` |

**关键差异**：GlobalPreview 含比率调整 UI（`api/backtestMulti.js → updateRatios()`）

---

## Task 5: XPL 数据分析模块

### 文件清单

| 文件 | 对应旧模板 |
|------|-----------|
| `src/views/xpl/Index.vue` | `xpl/index.html` — 数据分析首页 |
| `src/views/xpl/V1.vue` | `xpl/v1.html` — V1 回测数据分析 |

---

## Task 6: 管理后台模块（11 个页面）

### 文件清单

| 文件 | 对应旧模板 | 核心 API |
|------|-----------|---------|
| `src/views/admin/Dashboard.vue` | `admin/dashboard.html` | `admin.js → getDashboardOverview()` + Chart.js |
| `src/views/admin/Tasks.vue` | `admin/tasks.html` | `task.js` 全套 CRUD |
| `src/views/admin/Config.vue` | `admin/config.html` | `config.js` + `googleSheet.js` (Token 管理) |
| `src/views/admin/Logs.vue` | `admin/logs.html` | `config.js → getLogs()` + LogViewer |
| `src/views/admin/Templates.vue` | `admin/templates.html` | `template.js` CRUD |
| `src/views/admin/Results.vue` | `admin/results.html` | `template.js → getResults()` |
| `src/views/admin/ModelSummary.vue` | `admin/model_summary.html` | `admin.js → modelSummary()` |
| `src/views/admin/GoogleSheets.vue` | `admin/google_sheets.html` | `googleSheet.js` CRUD |
| `src/views/admin/Scheduler.vue` | `admin/scheduler.html` | `scheduler.js` CRUD + toggle/run |
| `src/views/admin/Users.vue` | `admin/users.html` | `auth.js → getUsers()` CRUD |
| `src/views/admin/Roles.vue` | `admin/roles.html` | `auth.js → getRoles()` + 权限分配 |
| `src/views/admin/Navigation.vue` | `admin/navigation.html` | `meta.js` 导航项 CRUD |

### 路由修正
- 将 `admin/model-summary` 路由的 component 从 `Results.vue` 改为 `ModelSummary.vue`

### Dashboard 组件分解
```
Dashboard.vue
├── StatCardGrid（已有）— 任务统计
├── el-row + el-col
│   ├── ChartPanel（已有）→ TaskTrendChart.vue（折线图）
│   ├── ChartPanel（已有）→ TaskStatusChart.vue（饼图）
│   └── ChartPanel（已有）→ TaskTypeChart.vue（柱状图）
└── RecentTasksTable.vue — 最近任务列表
```

---

## Task 7: 构建安全与生产就绪

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `vite.config.js` | 添加 manualChunks + 补充 `/backtest-multi-product/api` 代理 + chunkSizeWarningLimit |
| `src/App.vue` | 添加 ErrorBoundary 包裹 router-view |
| `src/components/ErrorBoundary.vue` | 新建 — 错误捕获 + 重试 UI |
| `nginx.conf` | 更新 SPA 路由 fallback（`try_files → /index.html`） |

### 防白屏措施
1. **ErrorBoundary 组件**：捕获渲染错误，展示友好提示 + 重试按钮
2. **Chunk 分包**：vendor（vue/vue-router）、element-plus、app 代码分离
3. **内联关键 CSS**：主题变量在 `<head>` 中内联，防止 FOUC
4. **路由懒加载**：所有页面已使用 `() => import()` 动态导入
5. **加载状态**：AppLayout 中 router-view 加载时显示骨架屏

### Vite 构建配置优化
```js
build: {
  outDir: 'dist',
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['vue', 'vue-router'],
        'element-plus': ['element-plus'],
      },
    },
  },
  chunkSizeWarningLimit: 1000,
}
```

### Vite 代理补充
当前 `vite.config.js` 缺少 `/backtest-multi-product/api` 代理，需添加：
```js
'/backtest-multi-product/api': {
  target: 'http://127.0.0.1:5000',
  changeOrigin: true,
},
```

---

## Task 8: 动画与打磨

- 页面切换 `<Transition name="fade-transform">` 动画
- 列表加载骨架屏
- 操作按钮 loading 状态
- el-notification 统一消息通知
- 表格空状态使用 EmptyState（已有）

---

## 实施顺序与依赖关系

```
Task 0 (样式系统)
  └→ Task 1 (布局 + 登录)
       ├→ Task 2 (任务模块) ← 核心业务，优先
       │    ├→ Task 3 (回测训练)
       │    └→ Task 4 (多产品回测)
       ├→ Task 5 (XPL)
       └→ Task 6 (管理后台)
            └→ Task 7 (构建安全) — 与 Task 2-6 并行
                 └→ Task 8 (动画打磨) — 最后
```

## 总文件清单

| 类别 | 文件数 |
|------|--------|
| 样式文件 | 3 |
| 布局组件 | 5 |
| 登录/403 | 2 |
| 任务模块 | 7 views + 3 composables + 4 子组件 |
| 回测模块 | 5 views + 1 composable |
| 多产品回测 | 5 views |
| XPL | 2 views |
| 管理后台 | 12 views |
| 构建/安全 | 2 (ErrorBoundary + vite config) |
| **合计** | **~51 个文件** |

## 验证方案

1. **Task 0-1 完成后**：`npm run dev` 启动，验证登录 → 侧边栏 → 主题切换
2. **Task 2 完成后**：创建 C3 任务 → 查看列表 → 查看详情/日志
3. **Task 3-6 完成后**：各模块 CRUD 功能验证
4. **Task 7 完成后**：`npm run build` 构建，检查 dist/ 产物，部署到 Nginx 验证 SPA 路由
5. **全程**：权限切换测试（管理员 vs 普通用户）、暗色主题一致性、移动端响应式
