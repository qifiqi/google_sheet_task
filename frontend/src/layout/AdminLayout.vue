<script setup lang="ts">
import { computed, onMounted, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Close, Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AdminSidebar from './AdminSidebar.vue'
import AdminTopbar from './AdminTopbar.vue'
import { useAuth } from '../composables/useAuth'
import { useNavigation } from '../composables/useNavigation'

const router = useRouter()
const route = useRoute()
const auth = useAuth()
const navigation = useNavigation()
const collapsed = shallowRef(false)

const activePath = computed(() => (route.name === 'Dashboard' ? '/admin' : route.path))
const visibleTabs = computed(() => {
  const leaves = navigation.navLeaves.value.slice(0, 10)
  const hasHome = leaves.some((item) => item.path === '/admin' || item.path === '/admin/')
  return hasHome ? leaves : [{ key: 'dashboard', label: '首页', path: '/admin' }, ...leaves]
})

function isDashboardPath(path: string) {
  return path === '/admin' || path === '/admin/' || path === '/'
}

function selectPath(path: string) {
  if (isDashboardPath(path)) {
    router.push({ name: 'Dashboard' })
    return
  }
  window.location.assign(path)
}

async function logout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.replace({ name: 'Login' })
}

onMounted(async () => {
  try {
    await navigation.loadNavigation()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载侧边栏失败')
  }
})
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

    <section class="admin-shell__main">
      <AdminTopbar
        :role-text="auth.roleText.value"
        :user="auth.currentUser.value"
        @logout="logout"
        @toggle-sidebar="collapsed = !collapsed"
      />

      <div class="admin-tabs">
        <button
          v-for="item in visibleTabs"
          :key="item.key"
          class="admin-tabs__item"
          :class="{ 'is-active': item.path && isDashboardPath(item.path) }"
          type="button"
          @click="item.path && selectPath(item.path)"
        >
          <el-icon><Promotion /></el-icon>
          <span>{{ item.label }}</span>
          <el-icon class="admin-tabs__close"><Close /></el-icon>
        </button>
      </div>

      <main class="admin-shell__content">
        <div class="admin-notice">
          <span class="admin-notice__icon"></span>
          <span>v3.0.0 版本正式上线！能力全面提升，配套完整交付方案，助力高效开发与商业落地。</span>
          <a href="/admin/tasks">立即体验演示</a>
        </div>
        <router-view />
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

.admin-tabs {
  height: var(--admin-tabs-height);
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 0 16px;
  overflow: hidden;
  background: var(--admin-surface);
  border-bottom: 1px solid var(--admin-border);
}

.admin-tabs__item {
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 11px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--admin-text-muted);
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.admin-tabs__item:hover,
.admin-tabs__item.is-active {
  background: var(--admin-primary-light);
  color: var(--admin-primary);
}

.admin-tabs__close {
  color: var(--admin-text-placeholder);
  font-size: 12px;
}

.admin-shell__content {
  height: calc(100vh - var(--admin-header-height) - var(--admin-tabs-height));
  padding: var(--admin-content-padding);
  overflow: auto;
}

.admin-notice {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-bottom: 20px;
  padding: 8px 14px;
  border: 1px solid var(--admin-primary-border);
  border-radius: 7px;
  background: var(--admin-primary-light);
  color: var(--admin-primary);
  font-size: 14px;
}

.admin-notice__icon {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: linear-gradient(135deg, var(--admin-primary), #10b981);
}

.admin-notice a {
  color: var(--admin-danger);
  font-weight: 600;
  text-decoration: none;
}

@media (max-width: 900px) {
  .admin-shell__main {
    margin-left: 0;
  }

  .admin-shell__content {
    padding: 14px;
  }

  .admin-notice {
    justify-content: flex-start;
    font-size: 12px;
  }
}
</style>
