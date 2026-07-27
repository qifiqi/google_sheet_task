<script setup lang="ts">
import { computed } from 'vue'
import type { ModelSummaryColumn, ModelSummaryItem } from '../../types/api'
import { formatDateTime } from '../../utils/format'
import { taskExecutionUrl, taskTypeText } from '../../utils/task'
import '../../styles/data/model-summary-table.css'

const props = defineProps<{ items: readonly ModelSummaryItem[]; columns: readonly ModelSummaryColumn[]; loading: boolean }>()
const tableItems = computed(() => [...props.items])

function formatMetric(value: string | number | null | undefined, format: string) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value !== 'number') return String(value)
  if (format === 'percent') return `${(value * 100).toFixed(2)}%`
  if (format === 'integer') return String(Math.round(value))
  return value.toFixed(2)
}

function metricClass(value: string | number | null | undefined) {
  const numberValue = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numberValue) || numberValue === 0) return ''
  return numberValue > 0 ? 'is-positive' : 'is-negative'
}

function parameterEntries(value: Record<string, unknown>) {
  return Object.entries(value || {}).filter(([, item]) => item !== null && item !== '' && !Array.isArray(item)).slice(0, 4)
}

const cSeriesDetailRoutes: Record<string, 'C3TaskDetail' | 'C4TaskDetail' | 'C5TaskDetail' | 'C7TaskDetail'> = {
  google_sheet: 'C3TaskDetail',
  google_sheet_c4: 'C4TaskDetail',
  google_sheet_c5: 'C5TaskDetail',
  google_sheet_c7: 'C7TaskDetail',
}

function cSeriesTaskDetailRoute(row: ModelSummaryItem) {
  const name = cSeriesDetailRoutes[String(row.task_type || '').toLowerCase()]
  return name ? { name, params: { taskId: row.task_id } } : null
}

function taskDetailUrl(row: ModelSummaryItem) {
  return taskExecutionUrl({ id: row.task_id, task_type: row.task_type })
}
</script>

<template>
  <el-table v-loading="loading" :data="tableItems" empty-text="暂无汇总数据" class="model-summary-table">
    <el-table-column label="标的" fixed min-width="140"><template #default="{ row }"><div class="model-summary-table__stock"><strong>{{ row.stock_code || '-' }}</strong><span>{{ row.stock_name || '-' }}</span></div></template></el-table-column>
    <el-table-column label="任务" min-width="190"><template #default="{ row }"><div class="model-summary-table__task"><RouterLink v-if="cSeriesTaskDetailRoute(row)" class="model-summary-table__task-link" :to="cSeriesTaskDetailRoute(row)!" :title="row.task_id">{{ row.task_name || row.task_id || '-' }}</RouterLink><a v-else class="model-summary-table__task-link" :href="taskDetailUrl(row)" :title="row.task_id">{{ row.task_name || row.task_id || '-' }}</a><span>{{ taskTypeText(row.task_type) }} · {{ row.model_name || row.model_key || '-' }}</span></div></template></el-table-column>
    <el-table-column label="ReturnBeats" width="126"><template #default="{ row }"><strong class="model-summary-table__metric" :class="metricClass(row.best_metric_value)">{{ formatMetric(row.best_metric_value, 'percent') }}</strong></template></el-table-column>
    <el-table-column label="结果时间" width="178"><template #default="{ row }">{{ formatDateTime(row.result_timestamp) }}</template></el-table-column>
    <el-table-column label="参数" min-width="190"><template #default="{ row }"><div class="model-summary-table__parameters"><el-tag v-for="[key, value] in parameterEntries(row.parameter_summary)" :key="key" effect="plain">{{ key }}: {{ value }}</el-tag><span v-if="!parameterEntries(row.parameter_summary).length">-</span></div></template></el-table-column>
    <el-table-column label="区间" min-width="150"><template #default="{ row }">{{ row.kline_range || row.year_label || '-' }}</template></el-table-column>
    <el-table-column v-for="column in columns" :key="column.key" :label="column.label" min-width="128"><template #default="{ row }"><span class="model-summary-table__metric" :class="metricClass(row.metrics[column.key])">{{ formatMetric(row.metrics[column.key], column.format) }}</span></template></el-table-column>
  </el-table>
</template>
