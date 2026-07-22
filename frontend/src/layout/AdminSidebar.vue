<script setup lang="ts">
import { computed } from 'vue'
import AppMenuItem from './AppMenuItem.vue'
import type { NavItem } from '../types/api'

const props = defineProps<{
  collapsed: boolean
  items: readonly NavItem[]
  activePath: string
}>()

const emit = defineEmits<{
  toggle: []
  select: [path: string]
}>()

function findOpenPath(items: readonly NavItem[], activePath: string, parents: string[] = []): string[] {
  for (const item of items) {
    if (item.path === activePath) return parents

    const openPath = findOpenPath(
      item.children || [],
      activePath,
      [...parents, item.path || item.key],
    )
    if (openPath.length) return openPath
  }

  return []
}

const defaultOpeneds = computed(() => findOpenPath(props.items, props.activePath))
</script>

<template>
  <aside class="admin-sidebar" :class="{ 'is-collapsed': collapsed }">
    <div class="admin-sidebar__brand">
      <div class="admin-sidebar__mark">J</div>
      <div v-show="!collapsed" class="admin-sidebar__brand-text">
        <strong>JaspilAdmin</strong>
        <span>Task Operations</span>
      </div>
    </div>

    <el-scrollbar class="admin-sidebar__scroll" always :min-size="36">
      <el-menu
        :collapse="collapsed"
        :collapse-transition="false"
        :default-active="activePath"
        :default-openeds="defaultOpeneds"
        unique-opened
        class="admin-sidebar__menu"
        @select="emit('select', $event)"
      >
        <AppMenuItem v-for="item in items" :key="item.key" :item="item" />
      </el-menu>
    </el-scrollbar>
  </aside>
</template>

<style scoped>
.admin-sidebar {
  width: var(--admin-sidebar-width);
  height: 100vh;
  flex: 0 0 auto;
  background: var(--admin-sidebar-bg);
  border-right: 1px solid var(--admin-border);
  transition: width 0.2s ease;
}

.admin-sidebar.is-collapsed {
  width: var(--admin-sidebar-collapsed-width);
}

.admin-sidebar__brand {
  height: var(--admin-header-height);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  border-bottom: 1px solid var(--admin-border);
}

.admin-sidebar__mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--admin-primary) 0%, #10b981 100%);
  color: #fff;
  font-weight: 800;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.2);
}

.admin-sidebar__brand-text {
  display: grid;
  min-width: 0;
  line-height: 1.1;
}

.admin-sidebar__brand-text strong {
  color: var(--admin-text);
  font-size: 17px;
  font-weight: 700;
}

.admin-sidebar__brand-text span {
  margin-top: 4px;
  color: var(--admin-text-placeholder);
  font-size: 11px;
}

.admin-sidebar__scroll {
  height: calc(100vh - var(--admin-header-height));
  padding: 10px 8px 14px;
}

.admin-sidebar__menu {
  border-right: 0;
}

.admin-sidebar__menu:not(.el-menu--collapse) {
  width: 100%;
}

:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  height: 44px;
  margin: 2px 0;
  border-radius: 6px;
  color: var(--admin-text-regular);
}

:deep(.el-menu-item.is-active) {
  background: var(--admin-primary-light);
  color: var(--admin-primary);
}

:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background: var(--admin-bg);
  color: var(--admin-primary);
}

:deep(.el-menu-item .el-icon),
:deep(.el-sub-menu__title .el-icon) {
  color: var(--admin-text-muted);
}

:deep(.el-menu-item.is-active .el-icon) {
  color: var(--admin-primary);
}

@media (max-width: 900px) {
  .admin-sidebar {
    position: fixed;
    z-index: 30;
    inset: 0 auto 0 0;
    width: min(var(--admin-sidebar-width), 80vw);
    box-shadow: 8px 0 24px rgba(15, 23, 42, 0.12);
    transform: translateX(0);
  }

  .admin-sidebar.is-collapsed {
    transform: translateX(-100%);
    border-right: 0;
    box-shadow: none;
  }
}
</style>
