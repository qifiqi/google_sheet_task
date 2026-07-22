<script setup lang="ts">
import { Close, Promotion } from '@element-plus/icons-vue'
import type { NavItem } from '../../types/api'

const props = defineProps<{
  items: readonly NavItem[]
  activePath: string
}>()

const emit = defineEmits<{
  select: [path: string]
  close: [item: NavItem]
}>()

function isDashboardPath(path?: string) {
  return path === '/admin' || path === '/admin/' || path === '/'
}

function isActive(path?: string) {
  if (!path) return false
  if (isDashboardPath(path) && isDashboardPath(props.activePath)) return true
  return path === props.activePath
}
</script>

<template>
  <nav class="admin-tabs" aria-label="页面标签">
    <div
      v-for="item in items"
      :key="item.key"
      class="admin-tabs__item"
      :class="{ 'is-active': isActive(item.path) }"
    >
      <button
        class="admin-tabs__main"
        type="button"
        @click="item.path && emit('select', item.path)"
      >
        <el-icon><Promotion /></el-icon>
        <span>{{ item.label }}</span>
      </button>
      <button
        v-if="!isDashboardPath(item.path)"
        class="admin-tabs__close"
        type="button"
        aria-label="关闭标签"
        @click="emit('close', item)"
      >
        <el-icon><Close /></el-icon>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.admin-tabs {
  height: var(--admin-tabs-height);
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 0 16px;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--admin-surface);
  border-bottom: 1px solid var(--admin-border);
  scrollbar-width: none;
}

.admin-tabs::-webkit-scrollbar { display: none; }

.admin-tabs__item {
  height: 30px;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  border-radius: 6px;
  background: transparent;
  color: var(--admin-text-muted);
  font-size: 13px;
  white-space: nowrap;
}

.admin-tabs__item:hover,
.admin-tabs__item.is-active {
  background: var(--admin-primary-light);
  color: var(--admin-primary);
}

.admin-tabs__main {
  height: 100%;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px 0 10px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.admin-tabs__close {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  margin-right: 4px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--admin-text-placeholder);
  cursor: pointer;
}

.admin-tabs__close:hover,
.admin-tabs__close:focus-visible {
  outline: 0;
  background: color-mix(in srgb, var(--admin-primary) 12%, transparent);
  color: var(--admin-primary);
}
</style>
