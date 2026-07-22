<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisRecord } from '../../types/analysis'
import '../../styles/analysis/analysis-chart-grid.css'

interface ChartSeriesSpec {
  label: string
  color: string
  tone: string
  source: string
  valueKey: string
}

interface ChartDefinition {
  key: string
  title: string
  subtitle: string
  wide?: boolean
  series: ChartSeriesSpec[]
}

const props = defineProps<{ result?: AnalysisRecord }>()

const chartDefinitions: ChartDefinition[] = [
  { key: 'annual-return', title: '年度收益率', subtitle: '指数 vs 模型', series: [series('指数', '#6B8DF5', 'primary', 'index_returns_rate', 'annual_return'), series('模型', '#38BDF8', 'cyan', 'start_returns_rate', 'annual_return')] },
  { key: 'annual-excess', title: '年超额收益', subtitle: '模型 - 指数', series: [series('年超额收益', '#2563EB', 'primary', 'excess_returns', 'annualized_return_diff')] },
  { key: 'annual-drawdown', title: '年度最大回撤', subtitle: '指数 vs 模型', series: [series('指数', '#F59E0B', 'warning', 'index_returns_rate', 'max_drawdown'), series('模型', '#EF4444', 'danger', 'start_returns_rate', 'max_drawdown')] },
  { key: 'kama', title: '卡玛比率', subtitle: '指数 vs 模型', series: [series('指数', '#6B8DF5', 'primary', 'kama', 'index_kama'), series('模型', '#38BDF8', 'cyan', 'kama', 'start_kama')] },
  { key: 'sortino', title: '索提诺比例', subtitle: '指数 vs 模型', series: [series('指数', '#6B8DF5', 'primary', 'sotino', 'index_sortino'), series('模型', '#38BDF8', 'cyan', 'sotino', 'start_sortino')] },
  { key: 'monthly-volatility', title: '月收益率波动率', subtitle: '指数 vs 模型', series: [series('指数', '#6B8DF5', 'primary', 'monthly_volatility', 'index'), series('模型', '#38BDF8', 'cyan', 'monthly_volatility', 'start')] },
  { key: 'monthly-excess', title: '月超额收益', subtitle: '模型 - 指数', wide: true, series: [series('月超额收益', '#2563EB', 'primary', 'monthly_excess_returns', 'excess_return')] },
  { key: 'sharpe', title: '夏普比率对比', subtitle: 'all / year_* / past_*', wide: true, series: [series('指数', '#6B8DF5', 'primary', 'sharpe', 'index_sharpe'), series('模型', '#38BDF8', 'cyan', 'sharpe', 'start_sharpe')] },
  { key: 'excess-metrics', title: '超额指标', subtitle: '夏普 / 索提诺', series: [series('超额夏普', '#2563EB', 'primary', 'excess_metrics', 'excess_sharpe'), series('超额索提诺', '#8B5CF6', 'violet', 'excess_metrics', 'excess_sortino')] },
  { key: 'repair-days', title: '最大回测修复天数', subtitle: 'index / start / excess', series: [series('指数', '#6B8DF5', 'primary', 'repair_days', 'index'), series('模型', '#38BDF8', 'cyan', 'repair_days', 'start'), series('超额', '#F59E0B', 'warning', 'repair_days', 'excess')] },
  { key: 'profit-monthly', title: '盈利月百分比', subtitle: '指数 vs 模型', wide: true, series: [series('指数', '#6B8DF5', 'primary', 'index_profit_monthly', 'value'), series('模型', '#38BDF8', 'cyan', 'start_profit_monthly', 'value')] },
]

const charts = computed(() => chartDefinitions.map((chart) => ({
  ...chart,
  series: chart.series.map((item, index) => ({ ...item, points: buildPoints(numbersFor(item), index) })),
})))
const virtual = computed(() => !props.result)

function series(label: string, color: string, tone: string, source: string, valueKey: string): ChartSeriesSpec {
  return { label, color, tone, source, valueKey }
}

function numbersFor(spec: ChartSeriesSpec) {
  const source = props.result?.[spec.source]
  if (Array.isArray(source)) {
    return source
      .filter((item): item is AnalysisRecord => isRecord(item) && String(item.year || '').toLowerCase() !== 'all')
      .map((item) => Number(item[spec.valueKey]))
      .filter(Number.isFinite)
  }
  if (isRecord(source)) {
    return Object.values(source)
      .map((item) => isRecord(item) ? Number(item[spec.valueKey]) : Number(item))
      .filter(Number.isFinite)
  }
  return []
}

function buildPoints(values: number[], offset: number) {
  if (values.length < 2) return placeholderPoints[offset % 3]
  const min = Math.min(...values)
  const range = Math.max(...values) - min || 1
  return values.map((value, index) => `${4 + (index * 92) / (values.length - 1)},${42 - ((value - min) / range) * 34}`).join(' ')
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const placeholderPoints = [
  '4,28 16,24 28,30 40,20 52,24 64,16 76,22 88,14 96,18',
  '4,32 16,28 28,22 40,26 52,18 64,22 76,14 88,20 96,12',
  '4,24 16,30 28,20 40,28 52,16 64,24 76,18 88,26 96,16',
]
</script>

<template>
  <section class="analysis-chart-grid" :class="{ 'is-virtual': virtual }" aria-label="V1 图表">
    <article v-for="chart in charts" :key="chart.key" class="analysis-chart-grid__card" :class="{ 'analysis-chart-grid__card--wide': chart.wide }">
      <header><h2>{{ chart.title }}</h2><span>{{ chart.subtitle }}</span></header>
      <svg class="analysis-chart-grid__canvas" viewBox="0 0 100 48" preserveAspectRatio="none" aria-hidden="true">
        <path v-for="line in [8, 20, 32, 44]" :key="line" :d="`M 0 ${line} H 100`" class="analysis-chart-grid__gridline" />
        <polyline v-for="item in chart.series" :key="item.label" :points="item.points" :stroke="item.color" fill="none" stroke-width="1.2" vector-effect="non-scaling-stroke" />
      </svg>
      <footer><span v-for="item in chart.series" :key="item.label"><i :class="`analysis-chart-grid__legend--${item.tone}`"></i>{{ item.label }}</span></footer>
    </article>
  </section>
</template>
