<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, shallowRef, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AdminTabs from '../components/admin/AdminTabs.vue'
import AdminSidebar from './AdminSidebar.vue'
import AdminTopbar from './AdminTopbar.vue'
import { useAuth } from '../composables/useAuth'
import { useNavigation } from '../composables/useNavigation'
import { legacyPathToVuePath } from '../router/migration-pages'
import type { NavItem } from '../types/api'

const CLOSED_TABS_KEY = 'admin_closed_tabs'

const router = useRouter()
const route = useRoute()
const auth = useAuth()
const navigation = useNavigation()
const collapsed = shallowRef(false)
const refreshKey = shallowRef(0)
const refreshing = shallowRef(false)
const closedTabKeys = shallowRef<Set<string>>(new Set())
const contentScrollbar = useTemplateRef<{ setScrollTop: (value: number) => void }>('contentScrollbar')
let refreshTimer: number | undefined

const activePath = computed(() => String(route.meta.navPath || (route.name === 'Dashboard' ? '/admin' : route.path)))
const breadcrumbItems = computed(() => {
  if (route.name === 'Dashboard') return ['仪表盘']
  const section = route.path.startsWith('/system')
    ? '系统模块'
    : route.path.startsWith('/scheduler')
      ? '调度模块'
      : route.path.startsWith('/model-summary')
        ? '数据模块'
        : route.path.startsWith('/google-sheet') || route.path.startsWith('/backtest') || route.path.startsWith('/xpl') || route.path.startsWith('/yule')
          ? '业务模块'
          : '任务模块'
  return [section, String(route.meta.title || '工作台')]
})
const visibleTabs = computed(() => {
  const leaves = navigation.navLeaves.value
  const dashboard = leaves.find((item) => isDashboardPath(item.path)) ?? {
    key: 'dashboard',
    label: '仪表盘',
    path: '/admin',
  }
  const unique = [
    dashboard,
    ...leaves.filter((item) => !isDashboardPath(item.path)),
  ].filter((item, index, items) => items.findIndex((candidate) => candidate.path === item.path) === index)

  return unique
    .filter((item) => isDashboardPath(item.path) || !closedTabKeys.value.has(item.key))
    .slice(0, 12)
})

function isDashboardPath(path?: string) {
  return path === '/admin' || path === '/admin/' || path === '/'
}

function persistClosedTabs() {
  sessionStorage.setItem(CLOSED_TABS_KEY, JSON.stringify([...closedTabKeys.value]))
}

function reopenTab(path: string) {
  const item = navigation.navLeaves.value.find((candidate) => candidate.path === path)
  if (!item || !closedTabKeys.value.has(item.key)) return
  const nextKeys = new Set(closedTabKeys.value)
  nextKeys.delete(item.key)
  closedTabKeys.value = nextKeys
  persistClosedTabs()
}

function selectPath(path: string) {
  reopenTab(path)
  const internalPath = legacyPathToVuePath[path]
  if (internalPath) {
    router.push(internalPath)
    return
  }
  window.location.assign(path)
}

function closeTab(item: NavItem) {
  if (isDashboardPath(item.path)) return
  closedTabKeys.value = new Set([...closedTabKeys.value, item.key])
  persistClosedTabs()
}

function refreshCurrentView() {
  if (refreshing.value) return
  refreshing.value = true
  refreshKey.value += 1
  window.clearTimeout(refreshTimer)
  refreshTimer = window.setTimeout(() => {
    refreshing.value = false
  }, 450)
}

function resetContentScroll() {
  nextTick(() => contentScrollbar.value?.setScrollTop(0))
}

async function logout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.replace({ name: 'Login' })
}

onMounted(async () => {
  resetContentScroll()

  if (window.innerWidth <= 900) {
    collapsed.value = true
  }

  try {
    const stored = JSON.parse(sessionStorage.getItem(CLOSED_TABS_KEY) || '[]')
    if (Array.isArray(stored)) {
      closedTabKeys.value = new Set(stored.filter((item): item is string => typeof item === 'string'))
    }
  } catch {
    sessionStorage.removeItem(CLOSED_TABS_KEY)
  }

  try {
    await navigation.loadNavigation()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载侧边栏失败')
  }
})

watch(() => route.fullPath, resetContentScroll)

onUnmounted(() => window.clearTimeout(refreshTimer))
</script>

<template>
  <div class="admin-shell">
    <AdminSidebar
      :active-path="activePath"
      :collapsed="collapsed"
      :items="navigation.navItems.value"
      @select="selectPath"
      @toggle="collapsed = !collapsed"
    />
    <button
      v-if="!collapsed"
      class="admin-shell__backdrop"
      type="button"
      aria-label="关闭侧边栏"
      @click="collapsed = true"
    ></button>

    <section class="admin-shell__main">
      <AdminTopbar
        :role-text="auth.roleText.value"
        :user="auth.currentUser.value"
        :nav-items="navigation.navLeaves.value"
        :breadcrumb-items="breadcrumbItems"
        :refreshing="refreshing"
        :sidebar-collapsed="collapsed"
        @logout="logout"
        @navigate="selectPath"
        @refresh="refreshCurrentView"
        @toggle-sidebar="collapsed = !collapsed"
      />

      <AdminTabs
        :items="visibleTabs"
        :active-path="activePath"
        @select="selectPath"
        @close="closeTab"
      />

      <main class="admin-shell__content">
        <el-scrollbar ref="contentScrollbar" class="admin-shell__content-scroll" always :min-size="36">
          <div class="admin-shell__content-inner">
            <router-view v-slot="{ Component }">
              <component :is="Component" :key="refreshKey" />
            </router-view>
          </div>
        </el-scrollbar>
      </main>
    </section>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
  display: flex;
  background: var(--admin-bg);
  color: var(--admin-text);
}

.admin-shell__main {
  min-width: 0;
  flex: 1;
}

.admin-shell__content {
  height: calc(100vh - var(--admin-header-height) - var(--admin-tabs-height));
  overflow: hidden;
}

.admin-shell__content-scroll {
  height: 100%;
}

.admin-shell__content-inner {
  min-width: 0;
  padding: var(--admin-content-padding);
}

.admin-shell__backdrop {
  display: none;
}

@media (max-width: 900px) {
  .admin-shell__main { margin-left: 0; }
  .admin-shell__content-inner { padding: 14px; }

  .admin-shell__backdrop {
    position: fixed;
    z-index: 25;
    inset: 0;
    left: min(var(--admin-sidebar-width), 80vw);
    display: block;
    padding: 0;
    border: 0;
    background: rgba(15, 23, 42, 0.34);
  }
}
</style>
