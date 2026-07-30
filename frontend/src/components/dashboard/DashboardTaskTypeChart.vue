<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '../common/BaseChart.vue'
import { useAdminPreferencesStore } from '../../stores/admin-preferences'
import type { DashboardTaskTypeStatusPoint } from '../../types/api'
import { taskStatusText } from '../../utils/format'
import { taskTypeText } from '../../utils/task'

const props = defineProps<{
  items: readonly DashboardTaskTypeStatusPoint[]
  days: number
}>()

const preferences = useAdminPreferencesStore()
const statuses = ['pending', 'running', 'completed', 'error', 'cancelled']
const colors: Record<string, string> = {
  pending: '#2563EB',
  running: '#F59E0B',
  completed: '#10B981',
  error: '#DC2626',
  cancelled: '#94A3B8',
}
const taskTypes = computed(() => [...new Set(props.items.map((item) => item.task_type))])
const chartOption = computed<EChartsCoreOption>(() => {
  const dark = preferences.theme === 'dark'
  const axisColor = dark ? '#9CA3AF' : '#64748B'
  const gridColor = dark ? '#30343B' : '#E2E8F0'
  return {
    grid: { top: 42, right: 16, bottom: 16, left: 16, containLabel: true },
    legend: { top: 0, icon: 'roundRect', textStyle: { color: axisColor } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: axisColor },
      splitLine: { lineStyle: { color: gridColor } },
    },
    yAxis: {
      type: 'category',
      data: taskTypes.value.map(taskTypeText),
      axisLabel: { color: axisColor, width: 110, overflow: 'truncate' },
      axisLine: { lineStyle: { color: gridColor } },
      axisTick: { show: false },
    },
    series: statuses.map((status) => ({
      name: taskStatusText(status),
      type: 'bar',
      stack: 'total',
      barMaxWidth: 24,
      itemStyle: { color: colors[status] },
      data: taskTypes.value.map((taskType) => props.items.find(
        (item) => item.task_type === taskType && item.status === status,
      )?.count ?? 0),
    })),
  }
})
</script>

<template>
  <el-card shadow="never" class="type-card">
    <template #header>
      <div class="type-card__header">
        <div>
          <strong>任务类型分布</strong>
          <span>近 {{ days }} 天创建任务的当前状态</span>
        </div>
      </div>
    </template>
    <div v-if="taskTypes.length" class="type-card__chart">
      <BaseChart :option="chartOption" :ariaLabel="`近 ${days} 天任务类型与状态分布图`" />
    </div>
    <el-empty v-else description="所选周期暂无任务" :image-size="72" />
  </el-card>
</template>

<style scoped>
.type-card__header > div {
  display: grid;
  gap: 4px;
}

.type-card__header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.type-card__header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.type-card__chart {
  height: 252px;
}
</style>
