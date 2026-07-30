<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '../common/BaseChart.vue'
import { useAdminPreferencesStore } from '../../stores/admin-preferences'
import { taskStatusText } from '../../utils/format'

const props = defineProps<{
  distribution: Record<string, number>
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
const items = computed(() => statuses
  .map((status) => ({
    name: taskStatusText(status),
    value: Number(props.distribution[status] ?? 0),
    itemStyle: { color: colors[status] },
  }))
  .filter((item) => item.value > 0))
const total = computed(() => items.value.reduce((sum, item) => sum + item.value, 0))
const chartOption = computed<EChartsCoreOption>(() => {
  const textColor = preferences.theme === 'dark' ? '#D1D5DB' : '#334155'
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 个任务 ({d}%)' },
    legend: { bottom: 0, icon: 'circle', textStyle: { color: textColor } },
    series: [{
      type: 'pie',
      radius: ['50%', '74%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { show: false },
      data: items.value,
    }],
  }
})
</script>

<template>
  <el-card shadow="never" class="status-card">
    <template #header>
      <div class="status-card__header">
        <div>
          <strong>任务状态</strong>
          <span>当前可见任务快照</span>
        </div>
        <strong>{{ total }}</strong>
      </div>
    </template>
    <div v-if="total" class="status-card__chart">
      <BaseChart :option="chartOption" ariaLabel="当前任务状态占比图" />
    </div>
    <el-empty v-else description="暂无任务状态数据" :image-size="72" />
  </el-card>
</template>

<style scoped>
.status-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.status-card__header > div {
  display: grid;
  gap: 4px;
}

.status-card__header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.status-card__header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.status-card__chart {
  height: 252px;
}
</style>
