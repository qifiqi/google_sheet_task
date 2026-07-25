<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { onKeyStroke, useFullscreen } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import {
  FullScreen,
  Menu,
  Moon,
  Refresh,
  Search,
  Sunny,
  SwitchButton,
} from '@element-plus/icons-vue'
import AdminSearchDialog from '../components/admin/AdminSearchDialog.vue'
import { useAdminPreferencesStore } from '../stores/admin-preferences'
import type { CurrentUser, NavItem } from '../types/api'

const props = defineProps<{
  user: CurrentUser | null
  roleText: string
  navItems: readonly NavItem[]
  breadcrumbItems: readonly string[]
  refreshing: boolean
  sidebarCollapsed: boolean
}>()

const emit = defineEmits<{
  toggleSidebar: []
  refresh: []
  navigate: [path: string]
  logout: []
}>()

const searchVisible = shallowRef(false)
const preferences = useAdminPreferencesStore()
const { isFullscreen, toggle: toggleBrowserFullscreen } = useFullscreen()
const themeIcon = computed(() => preferences.theme === 'dark' ? Sunny : Moon)
const themeLabel = computed(() => preferences.theme === 'dark' ? '切换浅色主题' : '切换深色主题')

function toggleTheme() {
  preferences.toggleTheme()
}

async function toggleFullscreen() {
  try {
    await toggleBrowserFullscreen()
  } catch {
    ElMessage.warning('浏览器未允许进入全屏')
  }
}

onKeyStroke('k', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
    event.preventDefault()
    searchVisible.value = true
  }
})
</script>

<template>
  <header class="admin-topbar">
    <div class="admin-topbar__left">
      <el-tooltip :content="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'" placement="bottom">
        <el-button
          :icon="Menu"
          text
          class="admin-icon-button"
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'"
          @click="emit('toggleSidebar')"
        />
      </el-tooltip>
      <el-tooltip content="刷新当前页面" placement="bottom">
        <el-button
          :icon="Refresh"
          :loading="props.refreshing"
          text
          class="admin-icon-button"
          aria-label="刷新当前页面"
          @click="emit('refresh')"
        />
      </el-tooltip>
      <el-breadcrumb separator="/" class="admin-topbar__breadcrumb" aria-label="面包屑">
        <el-breadcrumb-item v-for="item in breadcrumbItems" :key="item">{{ item }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="admin-topbar__right">
      <el-input
        class="admin-topbar__search"
        placeholder="搜索页面"
        :prefix-icon="Search"
        readonly
        aria-label="搜索页面"
        @click="searchVisible = true"
      />
      <el-tooltip :content="isFullscreen ? '退出全屏' : '进入全屏'" placement="bottom">
        <el-button
          :icon="FullScreen"
          text
          class="admin-icon-button"
          :aria-label="isFullscreen ? '退出全屏' : '进入全屏'"
          @click="toggleFullscreen"
        />
      </el-tooltip>
      <el-tooltip :content="themeLabel" placement="bottom">
        <el-button
          :icon="themeIcon"
          text
          class="admin-icon-button"
          :aria-label="themeLabel"
          @click="toggleTheme"
        />
      </el-tooltip>
      <el-dropdown trigger="click">
        <button class="admin-topbar__user" type="button">
          <span class="admin-topbar__avatar">{{ user?.username?.slice(0, 2).toUpperCase() || 'JA' }}</span>
          <span class="admin-topbar__user-text">
            <strong>{{ user?.username || '未登录' }}</strong>
            <small>{{ roleText }}</small>
          </span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>{{ roleText }}</el-dropdown-item>
            <el-dropdown-item divided :icon="SwitchButton" @click="emit('logout')">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>

  <AdminSearchDialog
    v-model="searchVisible"
    :items="navItems"
    @select="emit('navigate', $event)"
  />
</template>

<style scoped>
.admin-topbar {
  height: var(--admin-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 18px;
  background: var(--admin-header-bg);
  border-bottom: 1px solid var(--admin-border);
}

.admin-topbar__left,
.admin-topbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.admin-topbar__breadcrumb { margin-left: 12px; }
.admin-topbar__search { width: 176px; cursor: pointer; }
.admin-topbar__search :deep(.el-input__wrapper) { cursor: pointer; }

.admin-icon-button {
  width: 32px;
  height: 32px;
  color: var(--admin-text-muted);
}

.admin-topbar__user {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  color: var(--admin-text);
  cursor: pointer;
}

.admin-topbar__avatar {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--admin-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.admin-topbar__user-text {
  display: grid;
  text-align: left;
  line-height: 1.1;
}

.admin-topbar__user-text strong,
.admin-topbar__user-text small {
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-topbar__user-text strong {
  color: var(--admin-text);
  font-size: 13px;
}

.admin-topbar__user-text small {
  color: var(--admin-text-placeholder);
  font-size: 10px;
}

@media (max-width: 860px) {
  .admin-topbar__breadcrumb,
  .admin-topbar__search,
  .admin-topbar__user-text {
    display: none;
  }
}
</style>
