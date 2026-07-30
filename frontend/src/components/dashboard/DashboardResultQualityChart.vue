<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '../common/BaseChart.vue'
import { useAdminPreferencesStore } from '../../stores/admin-preferences'
import type { DashboardResultTrendPoint } from '../../types/api'

const props = defineProps<{
  items: readonly DashboardResultTrendPoint[]
  days: number
}>()

const preferences = useAdminPreferencesStore()
const total = computed(() => props.items.reduce((sum, item) => sum + item.success + item.failed, 0))
const chartOption = computed<EChartsCoreOption>(() => {
  const dark = preferences.theme === 'dark'
  const axisColor = dark ? '#9CA3AF' : '#64748B'
  const gridColor = dark ? '#30343B' : '#E2E8F0'
  return {
    color: ['#10B981', '#DC2626', '#2563EB'],
    grid: { top: 44, right: 24, bottom: 34, left: 16, containLabel: true },
    legend: { top: 4, icon: 'roundRect', textStyle: { color: axisColor } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: props.items.map((item) => dayjs(item.date).format('MM-DD')),
      axisLine: { lineStyle: { color: gridColor } },
      axisLabel: { color: axisColor },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        minInterval: 1,
        axisLabel: { color: axisColor },
        splitLine: { lineStyle: { color: gridColor } },
      },
      {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: axisColor, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '成功结果',
        type: 'bar',
        stack: 'results',
        barMaxWidth: 24,
        data: props.items.map((item) => item.success),
      },
      {
        name: '失败结果',
        type: 'bar',
        stack: 'results',
        barMaxWidth: 24,
        data: props.items.map((item) => item.failed),
      },
      {
        name: '成功率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: props.items.map((item) => {
          const count = item.success + item.failed
          return count ? Number(((item.success / count) * 100).toFixed(1)) : null
        }),
      },
    ],
  }
})
</script>

<template>
  <el-card shadow="never" class="quality-card">
    <template #header>
      <div class="quality-card__header">
        <div>
          <strong>结果质量</strong>
          <span>近 {{ days }} 天按结果写入时间统计</span>
        </div>
      </div>
    </template>
    <div v-if="total" class="quality-card__chart">
      <BaseChart :option="chartOption" :ariaLabel="`近 ${days} 天结果成功率趋势图`" />
    </div>
    <el-empty v-else description="所选周期暂无结果" :image-size="72" />
  </el-card>
</template>

<style scoped>
.quality-card__header > div {
  display: grid;
  gap: 4px;
}

.quality-card__header strong {
  color: var(--admin-text);
  font-size: 16px;
}

.quality-card__header span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.quality-card__chart {
  height: 252px;
}
</style>
