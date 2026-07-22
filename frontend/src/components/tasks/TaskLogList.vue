<script setup lang="ts">
import { shallowRef } from 'vue'
import type { TaskLogItem } from '../../types/api'
import { formatDateTime } from '../../utils/format'

const props = defineProps<{
  logs: TaskLogItem[]
  loading: boolean
  emptyDescription: string
}>()

const expandedKeys = shallowRef(new Set<string>())

function logKey(log: TaskLogItem, index: number) {
  return String(log.id ?? `${log.timestamp || 'unknown'}-${index}`)
}

function isLong(log: TaskLogItem) {
  return log.message.length > 90 || log.message.includes('\n')
}

function isExpanded(log: TaskLogItem, index: number) {
  return expandedKeys.value.has(logKey(log, index))
}

function toggle(log: TaskLogItem, index: number) {
  const key = logKey(log, index)
  const next = new Set(expandedKeys.value)
  next.has(key) ? next.delete(key) : next.add(key)
  expandedKeys.value = next
}

function levelClass(level?: string | null) {
  const value = String(level || '').toLowerCase()
  return value === 'error' || value === 'critical' ? 'is-danger' : value === 'warning' || value === 'warn' ? 'is-warning' : 'is-info'
}
</script>

<template>
  <div v-loading="loading" class="task-log-list">
    <el-empty v-if="!loading && !logs.length" :description="emptyDescription" :image-size="72" />
    <article v-for="(log, index) in logs" :key="logKey(log, index)" class="task-log-list__item">
      <time class="task-log-list__time">{{ formatDateTime(log.timestamp) }}</time>
      <span class="task-log-list__level" :class="levelClass(log.level)">{{ log.level || 'info' }}</span>
      <div class="task-log-list__content">
        <p class="task-log-list__message" :class="{ 'is-expanded': isExpanded(log, index) }">{{ log.message }}</p>
        <el-button v-if="isLong(log)" link type="primary" size="small" @click="toggle(log, index)">{{ isExpanded(log, index) ? '收起' : '展开' }}</el-button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.task-log-list { display: grid; gap: 0; min-height: 180px; max-height: calc(100vh - 260px); overflow: auto; }
.task-log-list__item { display: grid; grid-template-columns: 132px 56px minmax(0, 1fr); gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--admin-border-light); font-size: 12px; }
.task-log-list__time { color: var(--admin-text-muted); font-variant-numeric: tabular-nums; }
.task-log-list__level { color: var(--admin-primary); font-weight: 600; text-transform: uppercase; }
.task-log-list__level.is-danger { color: var(--admin-danger); }.task-log-list__level.is-warning { color: var(--admin-warning); }
.task-log-list__content { min-width: 0; }.task-log-list__message { display: -webkit-box; margin: 0; overflow: hidden; color: var(--admin-text-regular); line-height: 1.5; text-overflow: ellipsis; white-space: pre-wrap; word-break: break-word; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.task-log-list__message.is-expanded { display: block; overflow: visible; }
.task-log-list__content :deep(.el-button) { height: 18px; margin-top: 2px; padding: 0; font-size: 12px; }
@media (max-width: 480px) { .task-log-list__item { grid-template-columns: 1fr auto; }.task-log-list__content { grid-column: 1 / -1; } }
</style>
