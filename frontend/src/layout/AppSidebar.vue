<template>
  <el-menu
    :default-active="activeIndex"
    :collapse="collapsed"
    :collapse-transition="false"
    :unique-opened="true"
    background-color="transparent"
    :text-color="menuTextColor"
    :active-text-color="menuActiveTextColor"
    router
    class="app-sidebar"
  >
    <template v-for="item in navItems" :key="item.key">
      <el-menu-item v-if="item.path" :index="item.path">
        <span>{{ item.label }}</span>
      </el-menu-item>

      <el-sub-menu v-else :index="item.key">
        <template #title>
          <span>{{ item.label }}</span>
        </template>
        <el-menu-item
          v-for="child in item.children"
          :key="child.key"
          :index="child.path"
        >
          {{ child.label }}
        </el-menu-item>
      </el-sub-menu>
    </template>
  </el-menu>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useNavigation } from '@/composables/useNavigation'
import { useTheme } from '@/composables/useTheme'

defineProps({ collapsed: Boolean })
const { navItems, ensureNavLoaded } = useNavigation()
const { isDark } = useTheme()

function normalizeIndex(index = '') {
  return String(index).split('?')[0].split('#')[0]
}

function flattenNav(items = []) {
  return items.flatMap((item) => [
    item,
    ...(Array.isArray(item.children) ? flattenNav(item.children) : []),
  ])
}

const route = useRoute()
ensureNavLoaded()

const activeIndex = computed(() => {
  const currentPath = normalizeIndex(route.path)
  const matched = flattenNav(navItems.value)
    .map((item) => item.path)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .find((path) => {
      const normalizedPath = normalizeIndex(path)
      return normalizedPath === currentPath || currentPath.startsWith(`${normalizedPath}/`)
    })

  return matched || currentPath
})

const menuTextColor = computed(() => (isDark.value ? '#b8cae9' : '#c8d6ef'))
const menuActiveTextColor = computed(() => (isDark.value ? '#f8fbff' : '#ffffff'))
</script>

<style scoped>
.app-sidebar {
  height: 100%;
  border-right: none;
  padding: 12px 10px 10px;
}

.app-sidebar:not(.el-menu--collapse) {
  width: 240px;
}

.app-sidebar :deep(.el-menu-item),
.app-sidebar :deep(.el-sub-menu__title) {
  height: 46px;
  line-height: 46px;
  font-weight: 600;
  border-radius: 14px;
  margin-bottom: 6px;
  color: var(--app-sidebar-text) !important;
  transition: background-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.app-sidebar :deep(.el-menu-item:hover),
.app-sidebar :deep(.el-sub-menu__title:hover) {
  background: var(--app-sidebar-hover-bg) !important;
  color: var(--app-sidebar-active-text) !important;
  transform: translateX(2px);
}

.app-sidebar :deep(.el-menu-item.is-active) {
  background: var(--app-sidebar-active-bg) !important;
  color: var(--app-sidebar-active-text) !important;
  box-shadow: inset 0 0 0 1px var(--app-sidebar-border);
}

.app-sidebar :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: var(--app-sidebar-active-text) !important;
}

.app-sidebar :deep(.el-menu) {
  border-right: none;
  background: transparent;
}

@media (max-width: 767px) {
  .app-sidebar {
    padding-top: 4px;
  }

  .app-sidebar :deep(.el-menu-item),
  .app-sidebar :deep(.el-sub-menu__title) {
    height: 44px;
    line-height: 44px;
  }
}
</style>
