<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { DataAnalysis } from '@element-plus/icons-vue'
import type { AnalysisRecord } from '../../types/analysis'
import { analysisColumns, analysisRowsForSource, analysisScalarRows, formatCellValue } from '../../utils/analysis'
import '../../styles/analysis/analysis-detail-tabs.css'

interface DetailDefinition {
  name: string
  label: string
  sources: string[]
  columns: string[]
}

const props = defineProps<{ result?: AnalysisRecord }>()
const detailOpen = shallowRef<string[]>([])
const activeTab = shallowRef('annual')

const definitions: DetailDefinition[] = [
  { name: 'annual', label: '年度收益/回撤', sources: ['index_returns_rate', 'start_returns_rate'], columns: ['series', 'year', 'annual_return', 'max_drawdown', 'max_drawdown_date'] },
  { name: 'excess', label: '超额收益', sources: ['excess_returns'], columns: ['year', 'start_annualized_return', 'index_annualized_return', 'annualized_return_diff', 'start_end_date'] },
  { name: 'monthly-excess', label: '月超额收益', sources: ['monthly_excess_returns'], columns: ['year_month', 'index_return', 'start_return', 'excess_return'] },
  { name: 'kama', label: '卡玛比率', sources: ['kama'], columns: ['year', 'index_kama', 'start_kama', 'index_annualized_return', 'start_annualized_return', 'index_max_drawdown', 'start_max_drawdown'] },
  { name: 'sotino', label: '索提诺比例', sources: ['sotino'], columns: ['year', 'index_sortino', 'start_sortino', 'index_annualized_return', 'start_annualized_return'] },
  { name: 'sharpe', label: '夏普比率', sources: ['sharpe'], columns: ['key', 'index_sharpe', 'start_sharpe', 'index_mean_monthly_return', 'start_mean_monthly_return', 'start_date', 'end_date'] },
  { name: 'excess-metrics', label: '超额指标', sources: ['excess_metrics'], columns: ['key', 'name', 'value'] },
  { name: 'repair-days', label: '回测修复天数', sources: ['repair_days'], columns: ['key', 'value'] },
  { name: 'profit', label: '盈利统计', sources: ['index_profit_monthly', 'start_profit_monthly'], columns: ['series', 'year', 'value'] },
  { name: 'scalars', label: '关键标量', sources: [], columns: ['key', 'value'] },
  { name: 'sheet-result', label: 'Sheet 结果', sources: ['sheet_result'], columns: ['key', 'value'] },
]

const sections = computed(() => definitions.map((definition) => {
  const rows = definition.name === 'scalars'
    ? analysisScalarRows(props.result || {})
    : definition.sources.flatMap((source) => analysisRowsForSource(props.result || {}, source).map((row) => ({ series: sourceLabel(source), ...row })))
  return {
    ...definition,
    rows,
    visibleColumns: rows.length ? analysisColumns(rows) : definition.columns,
  }
}))
const rawJson = computed(() => props.result ? JSON.stringify(props.result, null, 2) : '{\n  "status": "等待分析"\n}')

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    index_returns_rate: '指数', start_returns_rate: '模型', index_profit_monthly: '指数', start_profit_monthly: '模型',
  }
  return labels[source] || source
}

function columnLabel(column: string) {
  const labels: Record<string, string> = {
    series: '数据组', year: '年份', year_month: '年月', key: '指标', name: '名称', value: '数值', annual_return: '年收益率', max_drawdown: '最大回撤', max_drawdown_date: '回撤日期', start_annualized_return: '模型年化', index_annualized_return: '指数年化', annualized_return_diff: '超额收益', start_end_date: '区间', index_return: '指数月收益', start_return: '模型月收益', excess_return: '超额差值', index_kama: '指数卡玛', start_kama: '模型卡玛', index_sortino: '指数索提诺', start_sortino: '模型索提诺', index_sharpe: '指数夏普', start_sharpe: '模型夏普', start_date: '开始', end_date: '结束',
  }
  return labels[column] || column
}

async function copyRawJson() {
  await navigator.clipboard.writeText(rawJson.value)
}
</script>

<template>
  <section class="analysis-detail-tabs">
    <el-collapse v-model="detailOpen">
      <el-collapse-item name="v1-details">
        <template #title>
          <div class="analysis-detail-tabs__title"><el-icon><DataAnalysis /></el-icon><strong>V1 数据明细</strong><span>展开查看完整分析表</span></div>
        </template>
        <el-tabs v-model="activeTab" tab-position="left">
          <el-tab-pane v-for="section in sections" :key="section.name" :label="section.label" :name="section.name">
            <el-table :data="section.rows.length ? section.rows : [{}]" class="analysis-detail-tabs__table">
              <el-table-column v-for="column in section.visibleColumns" :key="column" :label="columnLabel(column)" :min-width="150" show-overflow-tooltip>
                <template #default="{ row }">{{ row[column] === undefined ? '-' : formatCellValue(row[column]) }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="全量 JSON" name="raw">
            <div class="analysis-detail-tabs__raw-actions"><el-button text type="primary" @click="copyRawJson">复制 JSON</el-button></div>
            <pre class="analysis-detail-tabs__raw">{{ rawJson }}</pre>
          </el-tab-pane>
        </el-tabs>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>
