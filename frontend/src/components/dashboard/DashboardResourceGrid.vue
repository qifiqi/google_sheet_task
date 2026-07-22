<script setup lang="ts">
import { computed } from 'vue'
import {
  Calendar,
  Coin,
  Collection,
  Connection,
  Lock,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'
import type { DashboardResourceHealth } from '../../types/api'
import { formatDateTime } from '../../utils/format'

interface ResourceItem {
  key: string
  label: string
  value: string
  note: string
  icon: Component
  tone: 'primary' | 'success' | 'warning'
}

const props = defineProps<{
  resources: DashboardResourceHealth
}>()

const items = computed<ResourceItem[]>(() => {
  const result: ResourceItem[] = []
  const sheets = props.resources.google_sheets
  const tokens = props.resources.google_sheet_tokens
  const schedules = props.resources.scheduled_tasks
  const locks = props.resources.backtest_locks
  const catalog = props.resources.catalog

  if (sheets) {
    result.push({
      key: 'sheets',
      label: 'Google Sheet',
      value: `${sheets.available} / ${sheets.active}`,
      note: `可用 / 启用 · 占用 ${sheets.in_use}`,
      icon: Connection,
      tone: sheets.available ? 'success' : 'warning',
    })
  }
  if (tokens) {
    result.push({
      key: 'tokens',
      label: 'Token 池',
      value: `${tokens.available} / ${tokens.active}`,
      note: `可用 / 启用 · 当前占用 ${tokens.current_usage}`,
      icon: Coin,
      tone: tokens.available ? 'success' : 'warning',
    })
  }
  if (schedules) {
    result.push({
      key: 'schedules',
      label: '定时任务',
      value: `${schedules.active}`,
      note: schedules.next_run_at ? `下次 ${formatDateTime(schedules.next_run_at)}` : `运行中 ${schedules.running}`,
      icon: Calendar,
      tone: 'primary',
    })
  }
  if (locks) {
    result.push({
      key: 'locks',
      label: '回测资源锁',
      value: `${locks.active}`,
      note: locks.active ? '当前占用中的 Sheet' : '当前无资源锁',
      icon: Lock,
      tone: locks.active ? 'warning' : 'success',
    })
  }
  if (catalog) {
    result.push({
      key: 'catalog',
      label: '数据资产',
      value: `${catalog.best_summaries ?? catalog.result_summaries ?? 0}`,
      note: `最优汇总 · 模板 ${catalog.task_templates ?? 0} · 标的 ${catalog.stock_metadata ?? 0}`,
      icon: Collection,
      tone: 'primary',
    })
  }
  return result
})
</script>

<template>
  <section v-if="items.length" class="resource-section">
    <div class="resource-section__header">
      <div>
        <h2>资源健康</h2>
        <p>仅展示当前账号有权查看的运行资源</p>
      </div>
    </div>
    <div class="resource-grid">
      <el-card v-for="item in items" :key="item.key" shadow="never" class="resource-card">
        <span class="resource-card__icon" :class="`is-${item.tone}`">
          <component :is="item.icon" />
        </span>
        <div>
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.note }}</small>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.resource-section {
  display: grid;
  gap: 12px;
}

.resource-section__header h2 {
  margin: 0;
  color: var(--admin-text);
  font-size: 16px;
}

.resource-section__header p {
  margin: 3px 0 0;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
}

.resource-card :deep(.el-card__body) {
  min-height: 112px;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  padding: 16px;
}

.resource-card__icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: var(--admin-primary-light);
  color: var(--admin-primary);
}

.resource-card__icon.is-success {
  background: color-mix(in srgb, var(--admin-success) 12%, transparent);
  color: var(--admin-success);
}

.resource-card__icon.is-warning {
  background: color-mix(in srgb, var(--admin-warning) 13%, transparent);
  color: var(--admin-warning);
}

.resource-card__icon :deep(svg) {
  width: 18px;
  height: 18px;
}

.resource-card div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.resource-card span,
.resource-card small {
  overflow: hidden;
  color: var(--admin-text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-card strong {
  color: var(--admin-text);
  font-size: 21px;
  font-weight: 600;
}
</style>
