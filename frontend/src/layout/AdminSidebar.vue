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

const defaultOpeneds = computed(() => props.items.map((item) => item.path || item.key))
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

    <el-scrollbar class="admin-sidebar__scroll">
      <el-menu
        :collapse="collapsed"
        :collapse-transition="false"
        :default-active="activePath"
        :default-openeds="defaultOpeneds"
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
  width: 230px;
  height: 100vh;
  flex: 0 0 auto;
  background: #fff;
  border-right: 1px solid #edf0f5;
  transition: width 0.2s ease;
}

.admin-sidebar.is-collapsed {
  width: 72px;
}

.admin-sidebar__brand {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  border-bottom: 1px solid #edf0f5;
}

.admin-sidebar__mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: linear-gradient(135deg, #5d7cff 0%, #42d3c6 100%);
  color: #fff;
  font-weight: 800;
  box-shadow: 0 10px 24px rgba(93, 124, 255, 0.24);
}

.admin-sidebar__brand-text {
  display: grid;
  min-width: 0;
  line-height: 1.1;
}

.admin-sidebar__brand-text strong {
  color: #101828;
  font-size: 17px;
  font-weight: 700;
}

.admin-sidebar__brand-text span {
  margin-top: 4px;
  color: #98a2b3;
  font-size: 11px;
}

.admin-sidebar__scroll {
  height: calc(100vh - 60px);
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
  border-radius: 7px;
  color: #303849;
}

:deep(.el-menu-item.is-active) {
  background: #eef4ff;
  color: #4f76ff;
}

:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background: #f6f8fc;
  color: #4f76ff;
}

:deep(.el-menu-item .el-icon),
:deep(.el-sub-menu__title .el-icon) {
  color: #667085;
}

@media (max-width: 900px) {
  .admin-sidebar {
    position: fixed;
    z-index: 30;
    transform: translateX(0);
  }

  .admin-sidebar.is-collapsed {
    width: 0;
    overflow: hidden;
    border-right: 0;
  }
}
</style>
