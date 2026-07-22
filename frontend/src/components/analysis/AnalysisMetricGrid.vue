<script setup lang="ts">
import { computed } from 'vue'
import { Aim, DataAnalysis, Histogram, Odometer, TrendCharts, Trophy, WarningFilled } from '@element-plus/icons-vue'
import type { AnalysisRecord } from '../../types/analysis'
import { analysisMetrics, annualizedReturnDiff, formatAnalysisValue } from '../../utils/analysis'
import '../../styles/analysis/analysis-metric-grid.css'

const props = defineProps<{
  result?: AnalysisRecord
}>()

const metricIcons = [Trophy, TrendCharts, WarningFilled, DataAnalysis, Histogram, Odometer, Aim, TrendCharts]
const metricTones = ['primary', 'success', 'warning', 'danger', 'info', 'info', 'info', 'info']
const metrics = computed(() => analysisMetrics.map((metric, index) => ({
  ...metric,
  value: metric.key === 'annualized_return_diff'
    ? annualizedReturnDiff(props.result || {})
    : props.result?.[metric.key],
  icon: metricIcons[index],
  tone: metricTones[index],
})))
</script>

<template>
  <section class="analysis-metric-grid" aria-label="分析指标">
    <article v-for="metric in metrics" :key="metric.key" class="analysis-metric-grid__item">
      <div class="analysis-metric-grid__label">
        <span>{{ metric.label }}</span>
        <el-icon :class="`analysis-metric-grid__icon analysis-metric-grid__icon--${metric.tone}`"><component :is="metric.icon" /></el-icon>
      </div>
      <strong :class="{ 'is-placeholder': metric.value === null || metric.value === undefined }">{{ formatAnalysisValue(metric.value, metric.format) }}</strong>
      <small>{{ metric.key === 'annualized_return_diff' ? 'excess_returns[all]' : metric.key }}</small>
    </article>
  </section>
</template>
