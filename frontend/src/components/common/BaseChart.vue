<script setup lang="ts">
import { onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsCoreOption, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import '../../styles/components/base-chart.css'

use([BarChart, CanvasRenderer, GridComponent, LegendComponent, LineChart, PieChart, TooltipComponent])

const props = defineProps<{
  ariaLabel: string
  option: EChartsCoreOption
}>()

const chartElement = useTemplateRef<HTMLDivElement>('chartElement')
const chart = shallowRef<EChartsType | null>(null)

function renderChart() {
  chart.value?.setOption(props.option, { notMerge: true, lazyUpdate: true })
}

onMounted(() => {
  if (!chartElement.value) return
  chart.value = init(chartElement.value)
  renderChart()
})

useResizeObserver(chartElement, () => chart.value?.resize())
watch(() => props.option, renderChart, { deep: true })
onBeforeUnmount(() => chart.value?.dispose())
</script>

<template>
  <div ref="chartElement" class="base-chart" role="img" :aria-label="ariaLabel"></div>
</template>
