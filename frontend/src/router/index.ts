import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken } from '../api/http'
import { useAuth } from '../composables/useAuth'
import AdminLayout from '../layout/AdminLayout.vue'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'

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
          component: DashboardView,
          meta: { title: '工作台' },
        },
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
  const auth = useAuth()

  if (to.meta.public) {
    if (getAccessToken() && !auth.isAuthenticated.value) {
      await auth.loadCurrentUser()
    }
    return auth.isAuthenticated.value && to.name === 'Login' ? { name: 'Dashboard' } : true
  }

  if (!to.meta.requiresAuth) {
    return true
  }

  if (!getAccessToken()) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  const user = auth.isAuthenticated.value ? auth.currentUser.value : await auth.loadCurrentUser()
  if (!user) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  return true
})

export default router
