<script setup lang="ts">
import { computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '../common/BaseChart.vue'
import { useAdminPreferencesStore } from '../../stores/admin-preferences'
import type { DashboardTrendPoint } from '../../types/api'

const props = defineProps<{
  items: readonly DashboardTrendPoint[]
}>()

const emit = defineEmits<{
  refresh: []
}>()

const preferences = useAdminPreferencesStore()
const chartOption = computed<EChartsCoreOption>(() => {
  const dark = preferences.theme === 'dark'
  const axisColor = dark ? '#9CA3AF' : '#64748B'
  const gridColor = dark ? '#30343B' : '#E2E8F0'
  return {
    color: ['#2563EB', '#10B981'],
    grid: { top: 44, right: 20, bottom: 34, left: 12, containLabel: true },
    legend: { top: 4, icon: 'roundRect', textStyle: { color: axisColor } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: string | number) => `${Number(value || 0)} 个任务`,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.items.map((item) => dayjs(item.date).format('MM-DD')),
      axisLine: { lineStyle: { color: gridColor } },
      axisLabel: { color: axisColor },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      name: '任务数',
      nameTextStyle: { color: axisColor, padding: [0, 0, 0, 12] },
      axisLabel: { color: axisColor },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: [
      {
        name: '创建任务',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        areaStyle: { opacity: 0.08 },
        data: props.items.map((item) => item.created),
      },
      {
        name: '完成任务',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        areaStyle: { opacity: 0.08 },
        data: props.items.map((item) => item.completed),
      },
    ],
  }
})
</script>

<template>
  <el-card shadow="never" class="trend-card">
    <template #header>
      <div class="trend-card__header">
        <div>
          <strong>任务趋势</strong>
          <span>近 7 天创建与完成</span>
        </div>
        <el-tooltip content="刷新仪表盘" placement="top">
          <el-button :icon="Refresh" text type="primary" aria-label="刷新仪表盘" @click="emit('refresh')" />
        </el-tooltip>
      </div>
    </template>
    <div class="trend-card__chart">
      <BaseChart :option="chartOption" ariaLabel="近七天任务创建与完成趋势图" />
    </div>
  </el-card>
</template>

<style scoped>
.trend-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.trend-card__header > div {
  display: grid;
  gap: 4px;
}

.trend-card__header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.trend-card__header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.trend-card__chart {
  height: 252px;
}
</style>
