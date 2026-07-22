<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue'
import type { DashboardAlert } from '../../types/api'
import { formatDateTime } from '../../utils/format'

defineProps<{
  alerts: readonly DashboardAlert[]
}>()

const emit = defineEmits<{
  view: [taskId: string]
}>()
</script>

<template>
  <el-card shadow="never" class="alerts-card">
    <template #header>
      <div class="alerts-header">
        <div>
          <strong>最近告警</strong>
          <span>当前可见任务的异常日志</span>
        </div>
        <el-icon><WarningFilled /></el-icon>
      </div>
    </template>

    <div v-if="alerts.length" class="alerts-list">
      <button
        v-for="alert in alerts"
        :key="alert.id"
        class="alert-item"
        type="button"
        @click="emit('view', alert.task_id)"
      >
        <span class="alert-item__dot" :class="{ 'is-error': alert.level === 'error' }"></span>
        <span class="alert-item__content">
          <strong>{{ alert.task_name || alert.task_id }}</strong>
          <el-tooltip :content="alert.message" placement="top" :show-after="500">
            <span class="alert-item__message">{{ alert.message }}</span>
          </el-tooltip>
          <small>{{ formatDateTime(alert.timestamp) }}</small>
        </span>
      </button>
    </div>
    <el-empty v-else description="暂无异常日志" :image-size="72" />
  </el-card>
</template>

<style scoped>
.alerts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.alerts-header > div {
  display: grid;
  gap: 4px;
}

.alerts-header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.alerts-header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.alerts-header .el-icon {
  color: var(--admin-warning);
}

.alerts-list {
  display: grid;
}

.alert-item {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  gap: 11px;
  padding: 12px 0;
  border: 0;
  border-bottom: 1px solid var(--admin-border-light);
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.alert-item:first-child { padding-top: 0; }
.alert-item:last-child { padding-bottom: 0; border-bottom: 0; }

.alert-item__dot {
  width: 7px;
  height: 7px;
  margin-top: 7px;
  border-radius: 50%;
  background: var(--admin-warning);
}

.alert-item__dot.is-error { background: var(--admin-danger); }

.alert-item__content {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.alert-item__content strong,
.alert-item__message {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-item__content strong {
  color: var(--admin-text-regular);
  font-size: 13px;
}

.alert-item__message,
.alert-item__content small {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.alert-item:hover strong { color: var(--admin-primary); }
</style>
