import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/admin'
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    children: [
      {
        path: '',
        redirect: '/admin/dashboard'
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/admin/Dashboard.vue'),
        meta: { title: '仪表盘' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('../views/admin/Tasks.vue'),
        meta: { title: '任务管理' }
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('../views/admin/Config.vue'),
        meta: { title: '系统配置' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('../views/admin/Logs.vue'),
        meta: { title: '系统日志' }
      }
    ]
  },
  {
    path: '/google-sheet',
    component: () => import('../layouts/GoogleSheetLayout.vue'),
    children: [
      {
        path: '',
        redirect: '/google-sheet/index'
      },
      {
        path: 'index',
        name: 'GoogleSheetIndex',
        component: () => import('../views/google-sheet/Index.vue'),
        meta: { title: 'Google Sheet 管理' }
      },
      {
        path: 'create',
        name: 'GoogleSheetCreate',
        component: () => import('../views/google-sheet/Create.vue'),
        meta: { title: '创建任务' }
      },
      {
        path: 'detail',
        name: 'GoogleSheetDetail',
        component: () => import('../views/google-sheet/Detail.vue'),
        meta: { title: '任务详情' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - Google Sheet 任务管理系统`
  }
  next()
})

export default router
