import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../api/http'
import { useAuthStore } from '../stores/auth'
import AdminLayout from '../layout/AdminLayout.vue'
import LoginView from '../pages/auth/LoginView.vue'
import ModelSummaryView from '../pages/data/ModelSummaryView.vue'
import ResultListView from '../pages/tasks/ResultListView.vue'
import SchedulerView from '../pages/scheduler/SchedulerView.vue'
import TaskListView from '../pages/tasks/TaskListView.vue'
import TemplateListView from '../pages/tasks/TemplateListView.vue'
import XplJobListView from '../pages/tasks/XplJobListView.vue'
import AccessDeniedView from '../pages/shared/AccessDeniedView.vue'
import { migrationPlaceholderRoutes } from './migration-pages'

const router = createRouter({
  history: createWebHistory('/web/'),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/',
      component: AdminLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('../pages/dashboard/DashboardView.vue'),
          meta: { title: '工作台' },
        },
        {
          path: 'forbidden',
          name: 'AccessDenied',
          component: AccessDeniedView,
          meta: { title: '访问受限' },
        },
        {
          path: 'tasks',
          name: 'Tasks',
          component: TaskListView,
          meta: { title: '任务管理', navPath: '/admin/tasks' },
        },
        {
          path: 'templates',
          name: 'Templates',
          component: TemplateListView,
          meta: { title: '任务模板', navPath: '/admin/templates' },
        },
        {
          path: 'results',
          name: 'Results',
          component: ResultListView,
          meta: { title: '任务结果', navPath: '/admin/results' },
        },
        {
          path: 'xpl-analysis-jobs',
          name: 'XplAnalysisJobs',
          component: XplJobListView,
          meta: { title: 'XPL Job 运维', navPath: '/admin/xpl-analysis-jobs' },
        },
        {
          path: 'model-summary',
          name: 'ModelSummary',
          component: ModelSummaryView,
          meta: { title: '单模型汇总', navPath: '/admin/model-summary' },
        },
        {
          path: 'scheduler',
          name: 'Scheduler',
          component: SchedulerView,
          meta: { title: '定时任务', navPath: '/admin/scheduler' },
        },
        ...migrationPlaceholderRoutes,
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (getAccessToken() && !auth.isAuthenticated) {
      await auth.loadCurrentUser()
    }
    return auth.isAuthenticated && to.name === 'Login' ? { name: 'Dashboard' } : true
  }

  if (!to.meta.requiresAuth) {
    return true
  }

  if (!getAccessToken()) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  const user = auth.isAuthenticated ? auth.currentUser : await auth.loadCurrentUser()
  if (!user) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  const requiredPermission = typeof to.meta.permission === 'string' ? to.meta.permission : ''
  if (requiredPermission && !hasPermission(user.permissions || [], requiredPermission)) {
    return { name: 'AccessDenied', query: { redirect: to.fullPath } }
  }

  return true
})

function hasPermission(permissions: readonly string[], requiredPermission: string) {
  if (permissions.includes(requiredPermission)) {
    return true
  }
  if (requiredPermission.endsWith(':view')) {
    const managePermission = `${requiredPermission.slice(0, -':view'.length)}:manage`
    return permissions.includes(managePermission)
  }
  return false
}

export default router
