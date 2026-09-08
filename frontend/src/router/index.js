import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layout/AppLayout.vue'
import { useAuth } from '@/composables/useAuth'
import { useNavigation } from '@/composables/useNavigation'
import { goToMainWebLogin } from '@/config/auth'

const routes = [
  // 本地登录页已停用（Token 由主 Web 颁发，Token 缺失/失效时由
  // 路由守卫直接跳回主 Web 重新登录）；恢复本地登录时取消下方注释。
  // {
  //   path: '/login',
  //   name: 'Login',
  //   component: () => import('@/views/Login.vue'),
  //   meta: { public: true },
  // },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/Login.vue'), // 可替换为专用 403 页面
    meta: { public: true },
  },
  {
    path: '/',
    component: AppLayout,
    redirect: '/task/list',
    children: [
      // Task
      { path: 'task/list',       name: 'TaskList',      component: () => import('@/views/task/List.vue'),      meta: { title: '任务列表',       permission: 'task:view' } },
      { path: 'task/create/c3',  name: 'TaskCreateC3',  component: () => import('@/views/task/CreateC3.vue'),  meta: { title: '创建C3任务',     permission: 'task:create' } },
      { path: 'task/create/c4',  name: 'TaskCreateC4',  component: () => import('@/views/task/CreateC4.vue'),  meta: { title: '创建C4任务',     permission: 'task:create' } },
      { path: 'task/create/c5',  name: 'TaskCreateC5',  component: () => import('@/views/task/CreateC5.vue'),  meta: { title: '创建C5任务',     permission: 'task:create' } },
      { path: 'task/create/c31', name: 'TaskCreateC31', component: () => import('@/views/task/CreateC31.vue'), meta: { title: '创建C31批量任务', permission: 'task:create' } },
      { path: 'task/create',     name: 'TaskCreate',    component: () => import('@/views/task/Create.vue'),    meta: { title: '创建任务',       permission: 'task:create' } },
      { path: 'task/:id',        name: 'TaskDetail',    component: () => import('@/views/task/Detail.vue'),    meta: { title: '任务详情',       permission: 'task:view' } },
      // Backtest
      { path: 'backtest/create',            name: 'BacktestCreate',        component: () => import('@/views/backtest/Create.vue'),        meta: { title: '回测创建',   permission: 'backtest:create' } },
      { path: 'backtest/list',              name: 'BacktestList',          component: () => import('@/views/backtest/List.vue'),          meta: { title: '回测列表',   permission: 'backtest:view' } },
      { path: 'backtest/:id',               name: 'BacktestDetail',        component: () => import('@/views/backtest/Detail.vue'),        meta: { title: '回测详情',   permission: 'backtest:view' } },
      { path: 'backtest/:id/global-preview',name: 'BacktestGlobalPreview', component: () => import('@/views/backtest/GlobalPreview.vue'), meta: { title: '全局预览',   permission: 'backtest:view' } },
      { path: 'backtest/:id/result',        name: 'BacktestResult',        component: () => import('@/views/backtest/Result.vue'),        meta: { title: '回测结果',   permission: 'backtest:view' } },
      // Backtest Multi-Product
      { path: 'backtest-multi/list',              name: 'BacktestMultiList',          component: () => import('@/views/backtest-multi/List.vue'),          meta: { title: '多产品回测列表',   permission: 'backtest:view' } },
      { path: 'backtest-multi/create',            name: 'BacktestMultiCreate',        component: () => import('@/views/backtest-multi/Create.vue'),        meta: { title: '创建多产品回测',   permission: 'backtest:create' } },
      { path: 'backtest-multi/:id',               name: 'BacktestMultiDetail',        component: () => import('@/views/backtest-multi/Detail.vue'),        meta: { title: '多产品回测详情',   permission: 'backtest:view' } },
      { path: 'backtest-multi/:id/result',        name: 'BacktestMultiResult',        component: () => import('@/views/backtest-multi/Result.vue'),        meta: { title: '多产品回测结果',   permission: 'backtest:view' } },
      { path: 'backtest-multi/:id/global-preview',name: 'BacktestMultiGlobalPreview', component: () => import('@/views/backtest-multi/GlobalPreview.vue'), meta: { title: '多产品全局预览',   permission: 'backtest:view' } },
      // XPL — 无权限限制，登录即可访问
      { path: 'xpl',    name: 'XplIndex', component: () => import('@/views/xpl/Index.vue'), meta: { title: '数据分析' } },
      { path: 'xpl/v1', name: 'XplV1',   component: () => import('@/views/xpl/V1.vue'),    meta: { title: 'V1 分析' } },
      // Admin
      { path: 'admin',                name: 'Dashboard',       component: () => import('@/views/admin/Dashboard.vue'),    meta: { title: '仪表盘' } },
      { path: 'admin/tasks',          name: 'AdminTasks',      component: () => import('@/views/admin/Tasks.vue'),        meta: { title: '任务管理',          permission: 'task:view' } },
      { path: 'admin/config',         name: 'AdminConfig',     component: () => import('@/views/admin/Config.vue'),       meta: { title: '系统配置',          permission: 'config:view' } },
      { path: 'admin/logs',           name: 'AdminLogs',       component: () => import('@/views/admin/Logs.vue'),         meta: { title: '系统日志',          permission: 'task:view' } },
      { path: 'admin/templates',      name: 'AdminTemplates',  component: () => import('@/views/admin/Templates.vue'),    meta: { title: '模板管理',          permission: 'template:view' } },
      { path: 'admin/results',        name: 'AdminResults',    component: () => import('@/views/admin/Results.vue'),      meta: { title: '结果查询',          permission: 'task:view' } },
      { path: 'admin/google-sheets',  name: 'AdminGoogleSheets',component: () => import('@/views/admin/GoogleSheets.vue'),meta: { title: 'Google Sheets',    permission: 'google_sheet:view' } },
      { path: 'admin/scheduler',      name: 'AdminScheduler',  component: () => import('@/views/admin/Scheduler.vue'),    meta: { title: '定时任务',          permission: 'scheduler:view' } },
      // 用户 / 角色 / 路由表管理已随本地 RBAC 一并停用（后端接口已注释，
      // 菜单改由远程 GetUserRoleList 路由表下发）；恢复时取消下方注释。
      // { path: 'admin/users',          name: 'AdminUsers',      component: () => import('@/views/admin/Users.vue'),        meta: { title: '用户管理',          permission: 'user:view' } },
      // { path: 'admin/roles',          name: 'AdminRoles',      component: () => import('@/views/admin/Roles.vue'),        meta: { title: '角色管理',          permission: 'user:view' } },
      // { path: 'admin/navigation',    name: 'AdminNavigation', component: () => import('@/views/admin/Navigation.vue'),   meta: { title: '导航管理',          permission: 'navigation:view' } },
      { path: 'admin/model-summary',    name: 'ModelSummary', component: () => import('@/views/admin/Results.vue'),   meta: { title: '单模型汇总',          permission: 'modelsummary:view' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  // 单 Token 子服务模式: 支持主站跳转时通过 ?token= 携带登录态，
  // 写入 localStorage 后清除 URL 参数，避免 Token 泄漏到历史记录。
  if (to.query.token) {
    localStorage.setItem('access_token', String(to.query.token))
    const { token: _dropped, ...restQuery } = to.query
    return next({ path: to.path, query: restQuery, replace: true })
  }

  const token = localStorage.getItem('access_token')

  // 本地登录页已停用: 访问 /login 或无 Token 时统一跳回主 Web 重新登录，
  // 由主 Web 登录后通过 ?token= 跳转携带登录态返回本站。
  if (to.path === '/login') {
    goToMainWebLogin()
    return next(false)
  }

  if (to.meta.public) return next()
  if (!token) {
    goToMainWebLogin()
    return next(false)
  }

  // 确保用户信息已加载（含 permissions）
  const { user, fetchUser, hasPermission } = useAuth()
  if (!user.value) await fetchUser()

  const { ensureNavLoaded, getPagePermission } = useNavigation()
  await ensureNavLoaded()
  const perm = getPagePermission(to.fullPath)
  if (perm && !hasPermission(perm)) return next('/403')

  next()
})

export default router
