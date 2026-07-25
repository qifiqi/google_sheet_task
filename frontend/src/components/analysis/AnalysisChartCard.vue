<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '../common/BaseChart.vue'
import { useAdminPreferencesStore } from '../../stores/admin-preferences'
import type { AnalysisChart, AnalysisValueFormat } from '../../utils/analysis-charts'

const props = defineProps<{ chart: AnalysisChart }>()
const preferences = useAdminPreferencesStore()

const chartOption = computed<EChartsCoreOption>(() => {
  const dark = preferences.theme === 'dark'
  const axisColor = dark ? '#9CA3AF' : '#64748B'
  const gridColor = dark ? '#30343B' : '#E2E8F0'
  return {
    grid: { top: 48, right: 20, bottom: 46, left: 14, containLabel: true },
    legend: { top: 4, icon: 'roundRect', textStyle: { color: axisColor }, itemWidth: 12 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: string | number) => formatValue(Number(value), props.chart.valueFormat),
    },
    xAxis: {
      type: 'category',
      name: props.chart.xAxisName,
      nameLocation: 'middle',
      nameGap: 28,
      data: props.chart.labels,
      axisLine: { lineStyle: { color: gridColor } },
      axisTick: { show: false },
      axisLabel: { color: axisColor, rotate: props.chart.labels.length > 8 ? 32 : 0, interval: 'auto' },
      nameTextStyle: { color: axisColor },
    },
    yAxis: {
      type: 'value',
      name: props.chart.yAxisName,
      nameTextStyle: { color: axisColor, padding: [0, 0, 0, 8] },
      axisLabel: { color: axisColor, formatter: (value: string | number) => formatValue(Number(value), props.chart.valueFormat) },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: props.chart.series.map((series) => ({
      name: series.label,
      type: series.type,
      data: series.values.map((value) => props.chart.valueFormat === 'percent' && value !== null ? value * 100 : value),
      smooth: series.type === 'line',
      symbol: series.type === 'line' ? 'circle' : undefined,
      symbolSize: series.type === 'line' ? 7 : undefined,
      barMaxWidth: series.type === 'bar' ? 34 : undefined,
      lineStyle: { color: series.color, width: 2.5 },
      areaStyle: series.type === 'line' ? { color: series.color, opacity: 0.08 } : undefined,
      itemStyle: props.chart.colorByValue
        ? { color: (item: { value: number }) => item.value >= 0 ? '#10B981' : '#EF4444' }
        : { color: series.color },
    })),
  }
})

function formatValue(value: number, format: AnalysisValueFormat) {
  if (!Number.isFinite(value)) return '-'
  if (format === 'percent') return `${value.toFixed(2)}%`
  if (format === 'integer') return `${Math.round(value)} 天`
  return value.toFixed(3)
}
</script>

<template>
  <article class="analysis-chart-card" :class="{ 'analysis-chart-card--wide': chart.wide }">
    <header class="analysis-chart-card__header">
      <h2>{{ chart.title }}</h2>
      <span>{{ chart.subtitle }}</span>
    </header>
    <div v-if="chart.hasData" class="analysis-chart-card__canvas">
      <BaseChart :option="chartOption" :ariaLabel="`${chart.title}图表`" />
    </div>
    <el-empty v-else class="analysis-chart-card__empty" :image-size="48" description="该指标暂无数据" />
  </article>
</template>
