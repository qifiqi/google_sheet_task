<script setup lang="ts">
import { computed } from 'vue'
import { View } from '@element-plus/icons-vue'
import type { TaskResultItem, TaskResultModelSummary } from '../../types/api'
import { formatDateTime } from '../../utils/format'

const props = defineProps<{
  items: TaskResultItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  view: [result: TaskResultItem, modelKey: string]
}>()

interface TableRow {
  source: TaskResultItem
  model: TaskResultModelSummary
}

const rows = computed<TableRow[]>(() => props.items.flatMap((source) => {
  const models = source.summary?.models
  if (models?.length) return models.map((model) => ({ source, model }))
  return [{
    source,
    model: {
      key: 'default',
      code: '-',
      name: '-',
      analysis_status: source.summary?.analysis_status,
      metrics: source.summary?.metrics || {},
    },
  }]
}))

function metricClass(value?: string | number | null) {
  const numeric = Number.parseFloat(String(value ?? '').replace('%', ''))
  if (!Number.isFinite(numeric) || numeric === 0) return ''
  return numeric > 0 ? 'is-positive' : 'is-negative'
}

function metricText(value?: string | number | null) {
  if (value === null || value === undefined || value === '') return '-'
  const text = String(value)
  if (text.endsWith('%')) return text
  const numeric = Number(text)
  return Number.isFinite(numeric) ? numeric.toFixed(4) : text
}
</script>

<template>
  <el-table v-loading="loading" :data="rows" class="c-series-result-table" empty-text="暂无结果">
    <el-table-column label="标的与区间" min-width="190">
      <template #default="{ row }">
        <div class="c-series-result-table__subject">
          <strong>{{ row.source.summary?.stock_name ? `${row.source.summary.stock_code || '-'} / ${row.source.summary.stock_name}` : row.source.summary?.stock_code || '-' }}</strong>
          <span>{{ row.source.summary?.kline_date_range || row.source.summary?.period || '未记录区间' }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="模型" min-width="130"><template #default="{ row }"><div class="c-series-result-table__model"><strong>{{ row.model.name }}</strong><span v-if="row.model.code !== row.model.name">{{ row.model.code }}</span></div></template></el-table-column>
    <el-table-column label="参数组合" min-width="176">
      <template #default="{ row }">
        <div v-if="row.source.summary?.parameter_items?.length" class="c-series-result-table__parameters">
          <span v-for="item in row.source.summary.parameter_items" :key="`${row.source.id}-${item.label}`"><b>{{ item.label }}</b>{{ item.value }}</span>
        </div>
        <span v-else>-</span>
      </template>
    </el-table-column>
    <el-table-column label="Return" width="100"><template #default="{ row }"><span :class="metricClass(row.model.metrics.return)">{{ metricText(row.model.metrics.return) }}</span></template></el-table-column>
    <el-table-column label="Annualized" width="110"><template #default="{ row }"><span :class="metricClass(row.model.metrics.annualized)">{{ metricText(row.model.metrics.annualized) }}</span></template></el-table-column>
    <el-table-column label="Max DD%" width="106"><template #default="{ row }"><span :class="metricClass(row.model.metrics.max_drawdown)">{{ metricText(row.model.metrics.max_drawdown) }}</span></template></el-table-column>
    <el-table-column label="Index Return" width="118"><template #default="{ row }"><span :class="metricClass(row.model.metrics.index_return)">{{ metricText(row.model.metrics.index_return) }}</span></template></el-table-column>
    <el-table-column label="Index Annualized" width="136"><template #default="{ row }"><span :class="metricClass(row.model.metrics.index_annualized)">{{ metricText(row.model.metrics.index_annualized) }}</span></template></el-table-column>
    <el-table-column label="模型夏普" width="100"><template #default="{ row }"><span :class="metricClass(row.model.metrics.model_sharpe)">{{ metricText(row.model.metrics.model_sharpe) }}</span></template></el-table-column>
    <el-table-column label="状态" width="104"><template #default="{ row }"><el-tag :type="row.source.success ? 'success' : 'danger'" effect="light">{{ row.source.success ? '成功' : '失败' }}</el-tag></template></el-table-column>
    <el-table-column label="记录时间" width="176"><template #default="{ row }">{{ formatDateTime(row.source.timestamp) }}</template></el-table-column>
    <el-table-column fixed="right" label="操作" width="84"><template #default="{ row }"><el-button link type="primary" :icon="View" @click="emit('view', row.source, row.model.key)">详情</el-button></template></el-table-column>
  </el-table>
</template>

<style scoped>
.c-series-result-table { width: 100%; }
.c-series-result-table__subject { display: grid; gap: 4px; min-width: 0; }
.c-series-result-table__subject strong { overflow: hidden; color: var(--admin-text); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.c-series-result-table__subject span { overflow: hidden; color: var(--admin-text-muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.c-series-result-table__model { display: grid; gap: 3px; min-width: 0; }.c-series-result-table__model strong, .c-series-result-table__model span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.c-series-result-table__model strong { color: var(--admin-text); font-weight: 600; }.c-series-result-table__model span { color: var(--admin-text-muted); font-size: 12px; }
.c-series-result-table__parameters { display: flex; flex-wrap: wrap; gap: 6px; }
.c-series-result-table__parameters span { display: inline-flex; gap: 4px; max-width: 112px; min-height: 24px; padding: 0 7px; overflow: hidden; border: 1px solid var(--admin-primary-border); border-radius: 4px; color: var(--admin-text-regular); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.c-series-result-table__parameters b { color: var(--admin-text-muted); font-weight: 500; }
.is-positive { color: var(--admin-success); }.is-negative { color: var(--admin-danger); }
</style>
