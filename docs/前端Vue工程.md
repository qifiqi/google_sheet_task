# 前端 Vue 工程（frontend/）

## 技术栈

- Vue ^3.5 + vue-router ^4.6（history 模式）+ axios ^1.14
- UI 库：**Element Plus ^2.13 与 Naive UI ^2.44 双库并存**（main.js 全量注册两者；Element Plus 经 unplugin 自动按需引入组件）
- 构建：Vite ^8 + @vitejs/plugin-vue，sass，自动导入（AutoImport / Components）
- **无 pinia**：状态全部用 composable（useAuth / useNavigation）+ localStorage
- 入口标题："Jaspil 任务平台"

```bash
npm run dev      # localhost:3000，代理到 127.0.0.1:5000
npm run build    # 输出 dist/，由 Nginx 托管
```

## 目录结构

```
frontend/src/
  main.js / App.vue
  router/index.js           # 路由 + 全局守卫
  api/                      # 13 个模块：index.js(axios封装) + admin/auth/backtest/backtestMulti/
                            # config/database/googleSheet/meta/scheduler/task/template/xpl
  components/               # 11 个通用组件 + components/naive/ 5 个 Naive 变体
  composables/              # 7 个组合式函数
  layout/                   # AppHeader / AppLayout / AppSidebar
  views/                    # 页面（见下）
  directives/permission.js  # v-permission 指令
  styles/                   # index.scss / variables / mixins / naive-theme.js
  utils/                    # tradingDate.js（含 .test.mjs，无测试运行器）
```

### 通用组件（components/）

ChartPanel、CodeBlock、DataTableCard、EmptyState、FilterToolbar、LogViewer、MobileCardList、PageToolbar、StatCardGrid、StatusTag、TaskProgressCell；Naive 变体：NFilterToolbar、NPageToolbar、NProgressCell、NStatCardGrid、NStatusTag。

### Composables（composables/）

useAuth、useChartJs、useDebounce、useNavigation、usePolling、useResponsive、useTheme。

## 页面与路由（router/index.js）

根路径 `/` → AppLayout，redirect `/task/list`。路由分组：

- task：List / Detail / Create / CreateC3 / CreateC31 / CreateC4 / CreateC5
- backtest：List / Create / Detail / Result / GlobalPreview
- backtest-multi：List / Create / Detail / Result / GlobalPreview
- xpl：Index / V1（无权限限制，登录即可）
- admin：Dashboard / Tasks / Config / Templates / Results(含 /admin/model-summary) / Navigation / Logs / Scheduler / Users / Roles / GoogleSheets
- Login / 403

路由 `meta.permission` 携带权限码（task:view/create、backtest:*、config:view、scheduler:view 等），与后端 `app/config.py::PERMISSIONS` 对应。

### 路由守卫

检查 `localStorage.access_token` → `useAuth().fetchUser()` → `useNavigation().ensureNavLoaded()` → `getPagePermission(to.fullPath)` 校验，无权限跳 `/403`。

> **已知问题**：router 引用了 `views/backtest-multi/List.vue`、`Result.vue`、`GlobalPreview.vue`，但这 3 个文件当前不存在于 views/backtest-multi/ 下，访问对应路由会构建/运行报错，属于待补页面。

## API 层（api/index.js）

- `createHttpClient(config)`：axios 实例 + 请求拦截器注入 `Authorization: Bearer <access_token>`（localStorage）。
- 响应拦截器：直接返回 `res.data`；**401 时用 refresh_token 调 `POST /api/auth/refresh` 换新 token 并重放原请求**（isRefreshing + pendingRequests 队列防并发刷新）；刷新失败清 token 跳 `/login`。
- 默认实例 `api`：baseURL `/api`，timeout 30s；`rawApi`：无 baseURL，用于 `/admin/api/*`、`/backtest-training/api/*` 等完整路径。

## Vite 代理与构建集成

- dev 代理（vite.config.js）：`/api`、`/admin/api`、`/backtest-training/api`、`/xpl/analyze`、`/xpl/v1/analyze` → `http://127.0.0.1:5000`。新增后端页面 API 若前缀不同需手动补代理。
- **Flask 不托管 frontend/dist**：create_app 的 static_folder 仍是 `static/`，仓库中没有指向 dist 的 catch-all。生产形态是 Nginx 托管 dist + `/api/` 反代 Flask:5000（见 [部署运维.md](部署运维.md)）。

## 与 Jinja 旧前端的关系

双前端并存：Vue 覆盖任务管理、admin 面板等主要路由；Jinja 模板（templates/）仍承载登录页、backtest_training / backtest_multi_product / google_sheet 各 create+detail 页、xpl v1/v2、admin 的 model_summary 与 eastmoney_kline、yule、global_preview。两侧调用同一后端 API，改接口时两边都要核对。

## 修改前端时的检查点

1. 新增页面：views/ 加组件 + router 注册（带 meta.permission）+ api/ 模块 + 侧边导航（后端 NavigationMenuItem）。
2. 组件优先复用 components/ 与 naive 变体，保持 Element Plus / Naive 的使用场景一致。
3. 表单类页面注意 localStorage 恢复、模板回填、restart 回填、提交 payload 四处逻辑的一致性。
