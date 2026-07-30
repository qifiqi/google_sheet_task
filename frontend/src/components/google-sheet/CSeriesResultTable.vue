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

const visibleItems = computed(() => props.items)

function modelsFor(result: TaskResultItem): TaskResultModelSummary[] {
  const models = result.summary?.models
  if (models?.length) return models
  return [{
    key: 'default',
    code: '-',
    name: '-',
    analysis_status: result.summary?.analysis_status,
    metrics: result.summary?.metrics || {},
  }]
}

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

function stockCodeText(result: TaskResultItem) {
  return result.summary?.stock_code || '未记录代码'
}

function periodText(result: TaskResultItem) {
  return result.summary?.kline_date_range || result.summary?.period || '未记录区间'
}
</script>

<template>
  <div v-loading="loading" class="c-series-result-table">
    <el-empty v-if="!loading && !visibleItems.length" description="暂无结果" />

    <section v-for="result in visibleItems" :key="result.id" class="c-series-result-table__group">
      <header class="c-series-result-table__group-header">
        <div class="c-series-result-table__context">
          <div class="c-series-result-table__context-item c-series-result-table__context-item--subject">
            <span>股票代码</span>
            <strong>{{ stockCodeText(result) }}</strong>
          </div>
          <div class="c-series-result-table__context-item c-series-result-table__context-item--period">
            <span>K 线区间</span>
            <strong>{{ periodText(result) }}</strong>
          </div>
          <div class="c-series-result-table__context-item">
            <span>执行步骤</span>
            <strong>{{ result.step_index ?? '-' }}</strong>
          </div>
          <div class="c-series-result-table__context-item">
            <span>执行时间</span>
            <strong>{{ formatDateTime(result.timestamp) }}</strong>
          </div>
          <div class="c-series-result-table__context-item">
            <span>结果 ID</span>
            <strong>{{ result.id }}</strong>
          </div>
        </div>
        <div class="c-series-result-table__group-status c-series-result-table__context-item">
          <span>执行状态</span>
          <el-tag :type="result.success ? 'success' : 'danger'" effect="light">
            {{ result.success ? '成功' : '失败' }}
          </el-tag>
        </div>
      </header>

      <el-table :data="modelsFor(result)" border class="c-series-result-table__models">
        <el-table-column label="参数组合" min-width="280">
          <template #default>
            <div v-if="result.summary?.parameter_items?.length" class="c-series-result-table__parameters">
              <span v-for="item in result.summary.parameter_items" :key="`${result.id}-${item.label}`">
                <b>{{ item.label }}：</b>{{ item.value }}
              </span>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="Return" width="104"><template #default="{ row }"><span :class="metricClass(row.metrics.return)">{{ metricText(row.metrics.return) }}</span></template></el-table-column>
        <el-table-column label="Annualized" width="112"><template #default="{ row }"><span :class="metricClass(row.metrics.annualized)">{{ metricText(row.metrics.annualized) }}</span></template></el-table-column>
        <el-table-column label="Max DD%" width="108"><template #default="{ row }"><span :class="metricClass(row.metrics.max_drawdown)">{{ metricText(row.metrics.max_drawdown) }}</span></template></el-table-column>
        <el-table-column label="Index Return" width="118"><template #default="{ row }"><span :class="metricClass(row.metrics.index_return)">{{ metricText(row.metrics.index_return) }}</span></template></el-table-column>
        <el-table-column label="Index Annualized" width="138"><template #default="{ row }"><span :class="metricClass(row.metrics.index_annualized)">{{ metricText(row.metrics.index_annualized) }}</span></template></el-table-column>
        <el-table-column label="Index max dd" width="126"><template #default="{ row }"><span :class="metricClass(row.metrics.index_max_drawdown)">{{ metricText(row.metrics.index_max_drawdown) }}</span></template></el-table-column>
        <el-table-column label="i xpl" width="96"><template #default="{ row }"><span :class="metricClass(row.metrics.index_sharpe)">{{ metricText(row.metrics.index_sharpe) }}</span></template></el-table-column>
        <el-table-column label="s xpl" width="96"><template #default="{ row }"><span :class="metricClass(row.metrics.model_sharpe)">{{ metricText(row.metrics.model_sharpe) }}</span></template></el-table-column>
        <el-table-column fixed="right" label="操作" width="76">
          <template #default="{ row }">
            <el-button link type="primary" :icon="View" @click="emit('view', result, row.key)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.c-series-result-table {
  display: grid;
}

.c-series-result-table__group {
  display: grid;
  gap: 12px;
  padding: 14px 0 18px;
  border-bottom: 1px solid var(--admin-border-light);
}

.c-series-result-table__group:first-of-type {
  padding-top: 0;
}

.c-series-result-table__group:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.c-series-result-table__group-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 104px;
  align-items: stretch;
  gap: 8px;
}

.c-series-result-table__context {
  display: grid;
  grid-template-columns: minmax(160px, 1.1fr) minmax(210px, 1.3fr) repeat(3, minmax(100px, 0.65fr));
  gap: 8px;
  min-width: 0;
}

.c-series-result-table__context-item {
  display: grid;
  align-content: center;
  min-width: 0;
  min-height: 62px;
  gap: 4px;
  padding: 9px 11px;
  border: 1px solid var(--admin-border-light);
  border-radius: 5px;
  background: var(--admin-bg);
}

.c-series-result-table__context-item span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.c-series-result-table__context-item strong {
  overflow: hidden;
  color: var(--admin-text);
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.c-series-result-table__context-item--subject strong {
  font-weight: 600;
}

.c-series-result-table__group-status {
  justify-items: start;
}

.c-series-result-table__parameters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.c-series-result-table__parameters span {
  display: inline-flex;
  gap: 4px;
  min-height: 26px;
  padding: 0 8px;
  border: 1px solid var(--admin-primary-border);
  border-radius: 4px;
  color: var(--admin-text-regular);
  font-size: 12px;
  line-height: 24px;
}

.c-series-result-table__parameters b {
  color: var(--admin-text-muted);
  font-weight: 500;
}

.c-series-result-table__models {
  width: 100%;
}

.c-series-result-table__models :deep(.el-table__header .el-table__cell) {
  padding-top: 11px;
  padding-bottom: 11px;
}

.c-series-result-table__models :deep(.el-table__body .el-table__cell) {
  padding-top: 12px;
  padding-bottom: 12px;
}

.is-positive {
  color: var(--admin-success);
}

.is-negative {
  color: var(--admin-danger);
}

@media (max-width: 760px) {
  .c-series-result-table__group-header {
    grid-template-columns: 1fr;
  }

  .c-series-result-table__context {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 480px) {
  .c-series-result-table__context {
    grid-template-columns: 1fr;
  }
}
</style>
