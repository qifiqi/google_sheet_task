<script setup lang="ts">
import { computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import type { DashboardTrendPoint } from '../../types/api'

const props = defineProps<{
  items: readonly DashboardTrendPoint[]
}>()

const emit = defineEmits<{
  refresh: []
}>()

const chartPoints = computed(() => {
  const maxValue = Math.max(
    1,
    ...props.items.flatMap((item) => [item.created, item.completed]),
  )
  const denominator = Math.max(1, props.items.length - 1)
  return props.items.map((item, index) => {
    const x = 42 + (index * 596) / denominator
    return {
      ...item,
      x,
      createdY: 148 - (item.created / maxValue) * 112,
      completedY: 148 - (item.completed / maxValue) * 112,
      label: new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(item.date)),
    }
  })
})

const createdPolyline = computed(() => chartPoints.value.map((item) => `${item.x},${item.createdY}`).join(' '))
const completedPolyline = computed(() => chartPoints.value.map((item) => `${item.x},${item.completedY}`).join(' '))
</script>

<template>
  <el-card shadow="never" class="trend-card">
    <template #header>
      <div class="card-header">
        <div>
          <strong>任务趋势</strong>
          <span>近 7 天创建与完成</span>
        </div>
        <el-tooltip content="刷新仪表盘" placement="top">
          <el-button
            :icon="Refresh"
            text
            type="primary"
            aria-label="刷新仪表盘"
            @click="emit('refresh')"
          />
        </el-tooltip>
      </div>
    </template>

    <div class="trend-chart">
      <svg viewBox="0 0 680 190" role="img" aria-label="近七天任务创建与完成趋势">
        <line v-for="y in [36, 73, 110, 148]" :key="y" x1="42" x2="638" :y1="y" :y2="y" class="trend-chart__grid" />
        <polyline v-if="chartPoints.length" :points="createdPolyline" class="trend-chart__created" />
        <polyline v-if="chartPoints.length" :points="completedPolyline" class="trend-chart__completed" />
        <template v-for="point in chartPoints" :key="point.date">
          <circle :cx="point.x" :cy="point.createdY" r="4" class="trend-chart__created-dot" />
          <circle :cx="point.x" :cy="point.completedY" r="4" class="trend-chart__completed-dot" />
          <text :x="point.x" y="178" text-anchor="middle" class="trend-chart__label">{{ point.label }}</text>
        </template>
      </svg>
    </div>

    <div class="trend-legend">
      <span><i class="is-created"></i>创建任务</span>
      <span><i class="is-completed"></i>完成任务</span>
    </div>
  </el-card>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-header > div {
  display: grid;
  gap: 4px;
}

.card-header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.card-header span,
.trend-legend {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.trend-chart {
  min-height: 218px;
}

.trend-chart svg {
  width: 100%;
  height: 218px;
}

.trend-chart__grid {
  stroke: var(--admin-border-light);
  stroke-width: 1;
}

.trend-chart__created,
.trend-chart__completed {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.trend-chart__created { stroke: var(--admin-primary); }
.trend-chart__completed { stroke: var(--admin-success); }
.trend-chart__created-dot { fill: var(--admin-primary); }
.trend-chart__completed-dot { fill: var(--admin-success); }

.trend-chart__label {
  fill: var(--admin-text-placeholder);
  font-size: 11px;
}

.trend-legend {
  display: flex;
  justify-content: center;
  gap: 22px;
}

.trend-legend span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.trend-legend i {
  width: 18px;
  height: 3px;
  border-radius: 2px;
}

.trend-legend .is-created { background: var(--admin-primary); }
.trend-legend .is-completed { background: var(--admin-success); }
</style>
