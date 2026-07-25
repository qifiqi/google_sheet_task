<script setup lang="ts">
import { computed } from 'vue'
import AnalysisChartCard from './AnalysisChartCard.vue'
import type { AnalysisRecord } from '../../types/analysis'
import { buildAnalysisCharts } from '../../utils/analysis-charts'
import '../../styles/analysis/analysis-chart-grid.css'

const props = defineProps<{ result?: AnalysisRecord }>()
const charts = computed(() => buildAnalysisCharts(props.result))
</script>

<template>
  <section class="analysis-chart-grid" aria-label="V1 图表">
    <AnalysisChartCard v-for="chart in charts" :key="chart.key" :chart="chart" />
  </section>
</template>
