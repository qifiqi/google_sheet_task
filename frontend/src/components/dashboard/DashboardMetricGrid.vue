<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, DataLine, Tickets, WarningFilled } from '@element-plus/icons-vue'
import type { Component } from 'vue'
import type { DashboardExecutionHealth, DashboardSummary } from '../../types/api'

interface MetricCard {
  key: string
  label: string
  value: string
  note: string
  tone: 'primary' | 'success' | 'warning' | 'danger'
  icon: Component
}

const props = defineProps<{
  summary: DashboardSummary
  executionHealth?: DashboardExecutionHealth
}>()

const cards = computed<MetricCard[]>(() => [
  {
    key: 'tasks',
    label: '可见任务',
    value: props.summary.total_tasks.toLocaleString('zh-CN'),
    note: `待执行 ${props.summary.pending_tasks} · 已取消 ${props.summary.cancelled_tasks}`,
    tone: 'primary',
    icon: Tickets,
  },
  {
    key: 'results',
    label: '结果成功率',
    value: `${Number(props.executionHealth?.results.success_rate ?? 0).toFixed(1)}%`,
    note: `${props.executionHealth?.results.success ?? 0} / ${props.executionHealth?.results.total ?? 0} 条结果成功`,
    tone: 'success',
    icon: CircleCheck,
  },
  {
    key: 'running',
    label: '运行中任务',
    value: props.summary.running_tasks.toLocaleString('zh-CN'),
    note: `XPL 队列积压 ${props.executionHealth?.xpl_jobs.backlog ?? 0}`,
    tone: 'warning',
    icon: DataLine,
  },
  {
    key: 'errors',
    label: '异常任务',
    value: props.summary.error_tasks.toLocaleString('zh-CN'),
    note: `失败结果 ${props.executionHealth?.results.failed ?? 0} · XPL 异常 ${props.executionHealth?.xpl_jobs.error ?? 0}`,
    tone: 'danger',
    icon: WarningFilled,
  },
])
</script>

<template>
  <div class="metric-grid">
    <el-card
      v-for="card in cards"
      :key="card.key"
      shadow="never"
      class="metric-card"
      :class="`is-${card.tone}`"
    >
      <div class="metric-card__header">
        <span>{{ card.label }}</span>
        <span class="metric-card__icon"><component :is="card.icon" /></span>
      </div>
      <strong>{{ card.value }}</strong>
      <small>{{ card.note }}</small>
    </el-card>
  </div>
</template>

<style scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  position: relative;
  overflow: hidden;
}

.metric-card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--metric-accent, var(--admin-primary));
  content: '';
}

.metric-card.is-success { --metric-accent: var(--admin-success); }
.metric-card.is-warning { --metric-accent: var(--admin-warning); }
.metric-card.is-danger { --metric-accent: var(--admin-danger); }

.metric-card :deep(.el-card__body) {
  min-height: 132px;
  display: grid;
  align-content: space-between;
  gap: 8px;
  padding: 18px 20px 16px 22px;
}

.metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--admin-text-muted);
  font-size: 13px;
}

.metric-card__icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: color-mix(in srgb, var(--metric-accent, var(--admin-primary)) 12%, transparent);
  color: var(--metric-accent, var(--admin-primary));
}

.metric-card__icon :deep(svg) {
  width: 17px;
  height: 17px;
}

.metric-card strong {
  color: var(--admin-text);
  font-size: 28px;
  font-weight: 600;
}

.metric-card small {
  overflow: hidden;
  color: var(--admin-text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1240px) {
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .metric-grid { grid-template-columns: 1fr; }
}
</style>
