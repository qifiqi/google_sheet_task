<template>
  <div class="app-page backtest-result-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Result</div>
        <h2 class="page-title">回测结果</h2>
        <p class="page-description">查看并导出当前任务的 V1 回测分析结果，结构与旧版结果页保持一致。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button @click="loadResult">刷新</el-button>
        <el-button class="page-back-button" @click="$router.push(`/backtest/${taskId}`)">返回</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-row v-if="result" :gutter="12" class="backtest-result-page__summary-grid">
        <el-col
          v-for="card in summaryCards"
          :key="card.key"
          :xs="12"
          :sm="6"
          class="backtest-result-page__summary-col"
        >
          <el-card shadow="never" class="backtest-result-page__summary-card" :class="card.className">
            <div class="backtest-result-page__summary-inner">
              <div class="panel-note">{{ card.label }}</div>
              <div class="backtest-result-page__summary-value">{{ card.value }}</div>
              <div class="backtest-result-page__summary-key">{{ card.key }}</div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="result" shadow="never" class="page-section">
        <div class="section-heading">
          <div>
            <h3 class="section-title section-title--muted">V1 数据明细</h3>
            <div class="panel-note">按旧版结构保留年度收益、超额指标、比率和原始 JSON 多维查看。</div>
          </div>
          <div class="section-actions">
            <el-button size="small" @click="detailOpen = !detailOpen">
              {{ detailOpen ? '收起' : '展开' }}明细
            </el-button>
            <el-button size="small" type="primary" :disabled="!result" @click="exportResult">
              导出并下载
            </el-button>
          </div>
        </div>

        <div v-if="detailOpen" class="backtest-result-page__details">
          <el-tabs v-model="activeDetailTab" tab-position="left" class="backtest-result-page__tabs">
            <el-tab-pane label="年度收益/回撤" name="annual">
              <el-row :gutter="12">
                <el-col :xs="24" :lg="12" class="backtest-result-page__detail-col">
                  <div class="sub-card">
                    <div class="backtest-result-page__card-title">年度收益率对比</div>
                    <el-table :data="annualCompareRows" stripe border>
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="指数收益">
                        <template #default="{ row }"><span :class="colorClass(row.index_return)">{{ fmtPct(row.index_return) }}</span></template>
                      </el-table-column>
                      <el-table-column label="模型收益">
                        <template #default="{ row }"><span :class="colorClass(row.model_return)">{{ fmtPct(row.model_return) }}</span></template>
                      </el-table-column>
                      <el-table-column label="差值">
                        <template #default="{ row }"><span :class="colorClass(row.diff)">{{ fmtPct(row.diff) }}</span></template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-col>

                <el-col :xs="24" :lg="12" class="backtest-result-page__detail-col">
                  <div class="sub-card">
                    <div class="backtest-result-page__card-title">年度最大回撤对比</div>
                    <el-table :data="drawdownCompareRows" stripe border>
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="指数回撤">
                        <template #default="{ row }"><span class="text-danger">-{{ fmtPct(row.index_dd) }}</span></template>
                      </el-table-column>
                      <el-table-column label="模型回撤">
                        <template #default="{ row }"><span class="text-danger">-{{ fmtPct(row.model_dd) }}</span></template>
                      </el-table-column>
                      <el-table-column prop="dates" label="日期(指数/模型)" min-width="140" show-overflow-tooltip />
                    </el-table>
                  </div>
                </el-col>

                <el-col :xs="24" class="backtest-result-page__detail-col">
                  <div class="sub-card">
                    <div class="backtest-result-page__card-title">月超额收益百分比</div>
                    <el-table :data="result.monthly_excess_return_percentage || []" stripe border>
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="月超额收益占比">
                        <template #default="{ row }">{{ fmtPct(row.excess_return) }}</template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-col>
              </el-row>
            </el-tab-pane>

            <el-tab-pane label="超额收益" name="excess">
              <el-table :data="result.excess_returns || []" stripe border max-height="520">
                <el-table-column prop="year" label="Year" width="80" />
                <el-table-column label="模型年化">
                  <template #default="{ row }"><span :class="colorClass(row.start_annualized_return)">{{ fmtPct(row.start_annualized_return) }}</span></template>
                </el-table-column>
                <el-table-column label="指数年化">
                  <template #default="{ row }"><span :class="colorClass(row.index_annualized_return)">{{ fmtPct(row.index_annualized_return) }}</span></template>
                </el-table-column>
                <el-table-column label="超额">
                  <template #default="{ row }"><span :class="colorClass(row.annualized_return_diff)">{{ fmtPct(row.annualized_return_diff) }}</span></template>
                </el-table-column>
                <el-table-column prop="start_end_date" label="周期" min-width="140" show-overflow-tooltip />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="月超额收益" name="monthly_excess">
              <el-table :data="result.monthly_excess_returns || []" stripe border max-height="520">
                <el-table-column prop="year_month" label="年月" width="100" />
                <el-table-column label="指数月收益">
                  <template #default="{ row }"><span :class="colorClass(row.index_monthly_return)">{{ fmtPct(row.index_monthly_return) }}</span></template>
                </el-table-column>
                <el-table-column label="模型月收益">
                  <template #default="{ row }"><span :class="colorClass(row.start_monthly_return)">{{ fmtPct(row.start_monthly_return) }}</span></template>
                </el-table-column>
                <el-table-column label="超额差值">
                  <template #default="{ row }"><span :class="colorClass(row.monthly_excess_return_diff)">{{ fmtPct(row.monthly_excess_return_diff) }}</span></template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="卡玛比率" name="kama">
              <el-table :data="kamaRows" stripe border max-height="520">
                <el-table-column prop="year" label="年份" width="80" />
                <el-table-column label="指数Kama"><template #default="{ row }">{{ fmtNum(row.index_kama, 6) }}</template></el-table-column>
                <el-table-column label="模型Kama"><template #default="{ row }">{{ fmtNum(row.model_kama, 6) }}</template></el-table-column>
                <el-table-column label="指数年化"><template #default="{ row }">{{ fmtPct(row.index_annual) }}</template></el-table-column>
                <el-table-column label="模型年化"><template #default="{ row }">{{ fmtPct(row.model_annual) }}</template></el-table-column>
                <el-table-column label="指数回撤"><template #default="{ row }">{{ fmtPct(row.index_dd) }}</template></el-table-column>
                <el-table-column label="模型回撤"><template #default="{ row }">{{ fmtPct(row.model_dd) }}</template></el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="所提诺比率" name="sotino">
              <el-table :data="sotinoRows" stripe border max-height="520">
                <el-table-column prop="year" label="年份" width="80" />
                <el-table-column label="指数"><template #default="{ row }">{{ fmtNum(row.index_sotino, 6) }}</template></el-table-column>
                <el-table-column label="模型"><template #default="{ row }">{{ fmtNum(row.model_sotino, 6) }}</template></el-table-column>
                <el-table-column label="指数平均月收益"><template #default="{ row }">{{ fmtNum(row.index_avg_monthly, 6) }}</template></el-table-column>
                <el-table-column label="模型平均月收益"><template #default="{ row }">{{ fmtNum(row.model_avg_monthly, 6) }}</template></el-table-column>
                <el-table-column label="指数下行标准差"><template #default="{ row }">{{ fmtNum(row.index_downside_std, 6) }}</template></el-table-column>
                <el-table-column label="模型下行标准差"><template #default="{ row }">{{ fmtNum(row.model_downside_std, 6) }}</template></el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="夏普比率" name="sharpe">
              <el-table :data="sharpeRows" stripe border max-height="520">
                <el-table-column prop="period" label="区间" width="120" />
                <el-table-column label="指数夏普"><template #default="{ row }">{{ fmtNum(row.index_sharpe, 6) }}</template></el-table-column>
                <el-table-column label="模型夏普"><template #default="{ row }">{{ fmtNum(row.model_sharpe, 6) }}</template></el-table-column>
                <el-table-column label="指数平均月收益"><template #default="{ row }">{{ fmtPct(row.index_avg_monthly) }}</template></el-table-column>
                <el-table-column label="模型平均月收益"><template #default="{ row }">{{ fmtPct(row.model_avg_monthly) }}</template></el-table-column>
                <el-table-column label="指数月波动"><template #default="{ row }">{{ fmtPct(row.index_monthly_std) }}</template></el-table-column>
                <el-table-column label="模型月波动"><template #default="{ row }">{{ fmtPct(row.model_monthly_std) }}</template></el-table-column>
                <el-table-column label="指数年波动"><template #default="{ row }">{{ fmtPct(row.index_annual_std) }}</template></el-table-column>
                <el-table-column label="模型年波动"><template #default="{ row }">{{ fmtPct(row.model_annual_std) }}</template></el-table-column>
                <el-table-column prop="start_date" label="开始" width="100" />
                <el-table-column prop="end_date" label="结束" width="100" />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="超额指标" name="excess_metrics">
              <el-table :data="excessMetricsRows" stripe border max-height="520">
                <el-table-column prop="key" label="Key" width="220">
                  <template #default="{ row }"><code>{{ row.key }}</code></template>
                </el-table-column>
                <el-table-column prop="value" label="Value" />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="回测修复天数" name="repair_days">
              <el-table :data="repairDaysRows" stripe border max-height="520">
                <el-table-column prop="metric" label="Metric" width="140">
                  <template #default="{ row }"><code>{{ row.metric }}</code></template>
                </el-table-column>
                <el-table-column prop="value" label="Value" />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="盈利统计" name="profit">
              <el-row :gutter="12">
                <el-col :xs="24" :lg="12" class="backtest-result-page__detail-col">
                  <div class="sub-card">
                    <div class="backtest-result-page__card-title">盈利年百分比</div>
                    <el-table :data="profitAnnualRow" stripe border>
                      <el-table-column label="指数"><template #default="{ row }">{{ fmtPct(row.index) }}</template></el-table-column>
                      <el-table-column label="模型"><template #default="{ row }">{{ fmtPct(row.model) }}</template></el-table-column>
                    </el-table>
                  </div>
                </el-col>

                <el-col :xs="24" :lg="12" class="backtest-result-page__detail-col">
                  <el-row :gutter="12">
                    <el-col :xs="24" class="backtest-result-page__detail-col">
                      <div class="sub-card">
                        <div class="backtest-result-page__card-title">指数盈利月占比</div>
                        <el-table :data="result.index_profit_monthly || []" stripe border max-height="220">
                          <el-table-column prop="year" label="Year" width="80" />
                          <el-table-column label="占比">
                            <template #default="{ row }">{{ fmtPct(row.profit_monthly_percentage) }}</template>
                          </el-table-column>
                        </el-table>
                      </div>
                    </el-col>

                    <el-col :xs="24" class="backtest-result-page__detail-col">
                      <div class="sub-card">
                        <div class="backtest-result-page__card-title">模型盈利月占比</div>
                        <el-table :data="result.start_profit_monthly || []" stripe border max-height="220">
                          <el-table-column prop="year" label="Year" width="80" />
                          <el-table-column label="占比">
                            <template #default="{ row }">{{ fmtPct(row.profit_monthly_percentage) }}</template>
                          </el-table-column>
                        </el-table>
                      </div>
                    </el-col>
                  </el-row>
                </el-col>
              </el-row>
            </el-tab-pane>

            <el-tab-pane label="关键标量" name="scalars">
              <el-table :data="scalarsRows" stripe border max-height="520">
                <el-table-column prop="key" label="Key" width="280">
                  <template #default="{ row }"><code>{{ row.key }}</code></template>
                </el-table-column>
                <el-table-column prop="name" label="Name" width="180" />
                <el-table-column prop="value" label="Value" />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="Sheet 结果" name="sheet_result">
              <el-table :data="sheetResultRows" stripe border max-height="520">
                <el-table-column prop="key" label="Key" width="220">
                  <template #default="{ row }"><code>{{ row.key }}</code></template>
                </el-table-column>
                <el-table-column prop="value" label="Value" show-overflow-tooltip />
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="全量 JSON" name="raw">
              <div class="backtest-result-page__raw-actions">
                <el-button size="small" @click="copyRawJson">复制</el-button>
              </div>
              <pre class="code-block backtest-result-page__raw-code">{{ JSON.stringify(result, null, 2) }}</pre>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-card>

      <el-empty v-if="!loading && !result" description="暂无回测结果" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTaskResult } from '@/api/backtest'
import { exportXplResult } from '@/api/xpl'

const route = useRoute()
const taskId = route.params.id
const loading = ref(false)
const result = ref(null)
const detailOpen = ref(false)
const activeDetailTab = ref('annual')

function fmtPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

function fmtNum(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return String(Math.round(Number(value)))
}

function colorClass(value) {
  return (Number(value) || 0) >= 0 ? 'text-success' : 'text-danger'
}

const excessReturnsAll = computed(() => {
  if (!result.value) return '-'
  const entry = Array.isArray(result.value.excess_returns)
    ? result.value.excess_returns.find((item) => String(item.year) === 'all')
    : null
  return entry ? fmtPct(entry.annualized_return_diff) : '-'
})

const summaryCards = computed(() => [
  { key: 'outperform_year', label: '跑赢年份', value: result.value ? fmtPct(result.value.outperform_year) : '-', className: 'is-primary' },
  { key: 'monthly_excess_volatility', label: '月超额波动率', value: result.value ? fmtNum(result.value.monthly_excess_volatility, 4) : '-', className: 'is-success' },
  { key: 'excess_drawdown_winning_rate', label: '超额回撤胜率', value: result.value ? fmtPct(result.value.excess_drawdown_winning_rate) : '-', className: 'is-warning' },
  { key: 'excess_returns[all]', label: '年超额收益(整体)', value: excessReturnsAll.value, className: 'is-danger' },
  { key: 'index_profit_annual', label: '指数盈利年%', value: result.value ? fmtPct(result.value.index_profit_annual) : '-', className: 'is-neutral' },
  { key: 'start_profit_annual', label: '模型盈利年%', value: result.value ? fmtPct(result.value.start_profit_annual) : '-', className: 'is-neutral' },
  { key: 'index_monthly_return_volatility', label: '指数月波动率', value: result.value ? fmtNum(result.value.index_monthly_return_volatility, 6) : '-', className: 'is-neutral' },
  { key: 'start_monthly_return_volatility', label: '模型月波动率', value: result.value ? fmtNum(result.value.start_monthly_return_volatility, 6) : '-', className: 'is-neutral' }
])

const annualCompareRows = computed(() => {
  if (!result.value) return []
  const indexMap = new Map()
  const modelMap = new Map()
  ;(result.value.index_returns_rate || []).forEach((item) => {
    if (String(item.year) !== 'all') indexMap.set(String(item.year), item.annual_return)
  })
  ;(result.value.start_returns_rate || []).forEach((item) => {
    if (String(item.year) !== 'all') modelMap.set(String(item.year), item.annual_return)
  })
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()])).sort()
  return years.map((year) => {
    const indexReturn = indexMap.get(year)
    const modelReturn = modelMap.get(year)
    return {
      year,
      index_return: indexReturn,
      model_return: modelReturn,
      diff: modelReturn != null && indexReturn != null ? modelReturn - indexReturn : null
    }
  })
})

const drawdownCompareRows = computed(() => {
  if (!result.value) return []
  const indexMap = new Map()
  const modelMap = new Map()
  ;(result.value.index_maximum_drawdown?.year_maximum_drawdown || []).forEach((item) => {
    if (String(item.year) !== 'all') indexMap.set(String(item.year), item)
  })
  ;(result.value.start_maximum_drawdown?.year_maximum_drawdown || []).forEach((item) => {
    if (String(item.year) !== 'all') modelMap.set(String(item.year), item)
  })
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()])).sort()
  return years.map((year) => {
    const indexItem = indexMap.get(year)
    const modelItem = modelMap.get(year)
    return {
      year,
      index_dd: indexItem?.drawdown,
      model_dd: modelItem?.drawdown,
      dates: `${indexItem?.date || '-'} / ${modelItem?.date || '-'}`
    }
  })
})

const kamaRows = computed(() => {
  if (!result.value) return []
  const indexMap = new Map()
  const modelMap = new Map()
  ;(result.value.index_kama_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') indexMap.set(String(item.year), item)
  })
  ;(result.value.start_kama_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') modelMap.set(String(item.year), item)
  })
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()])).sort()
  return years.map((year) => {
    const indexItem = indexMap.get(year)
    const modelItem = modelMap.get(year)
    return {
      year,
      index_kama: indexItem?.kama_ratio,
      model_kama: modelItem?.kama_ratio,
      index_annual: indexItem?.annualized_return,
      model_annual: modelItem?.annualized_return,
      index_dd: indexItem?.drawdown,
      model_dd: modelItem?.drawdown
    }
  })
})

const sotinoRows = computed(() => {
  if (!result.value) return []
  const indexMap = new Map()
  const modelMap = new Map()
  ;(result.value.index_sotino_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') indexMap.set(String(item.year), item)
  })
  ;(result.value.start_sotino_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') modelMap.set(String(item.year), item)
  })
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()])).sort()
  return years.map((year) => {
    const indexItem = indexMap.get(year)
    const modelItem = modelMap.get(year)
    return {
      year,
      index_sotino: indexItem?.sotino_ratio,
      model_sotino: modelItem?.sotino_ratio,
      index_avg_monthly: indexItem?.average_monthly_annualized_return,
      model_avg_monthly: modelItem?.average_monthly_annualized_return,
      index_downside_std: indexItem?.downside_standard_deviation,
      model_downside_std: modelItem?.downside_standard_deviation
    }
  })
})

const sharpeRows = computed(() => {
  if (!result.value) return []
  const indexRatios = result.value.index_sharpe_ratios || {}
  const modelRatios = result.value.start_sharpe_ratios || {}
  const keys = Array.from(new Set([...Object.keys(indexRatios), ...Object.keys(modelRatios)])).sort()
  return keys.map((key) => {
    const indexItem = indexRatios[key]
    const modelItem = modelRatios[key]
    const base = indexItem || modelItem
    return {
      period: key,
      index_sharpe: indexItem?.sharpe_ratio,
      model_sharpe: modelItem?.sharpe_ratio,
      index_avg_monthly: indexItem?.avg_monthly_return,
      model_avg_monthly: modelItem?.avg_monthly_return,
      index_monthly_std: indexItem?.monthly_std_dev,
      model_monthly_std: modelItem?.monthly_std_dev,
      index_annual_std: indexItem?.annual_std_dev,
      model_annual_std: modelItem?.annual_std_dev,
      start_date: base?.start_date,
      end_date: base?.end_date
    }
  })
})

const excessMetricsRows = computed(() => {
  if (!result.value) return []
  return [
    { key: 'excess_sharp', value: fmtNum(result.value.excess_sharp, 6) },
    { key: 'excess_of_promissory_note', value: fmtNum(result.value.excess_of_promissory_note, 6) }
  ]
})

const repairDaysRows = computed(() => {
  if (!result.value) return []
  return [
    ['index', result.value.index_maximum_number_of_backtest_repair_days],
    ['start', result.value.start_maximum_number_of_backtest_repair_days],
    ['excess', result.value.excess_maximum_number_of_backtest_repair_days]
  ]
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([metric, value]) => ({ metric, value: fmtInt(value) }))
})

const profitAnnualRow = computed(() => {
  if (!result.value) return []
  return [{ index: result.value.index_profit_annual, model: result.value.start_profit_annual }]
})

const SCALAR_NAME_MAP = {
  outperform_year: '跑赢年份',
  monthly_excess_volatility: '月超额波动率',
  excess_drawdown_winning_rate: '超额回撤胜率',
  excess_sharp: '超额夏普',
  excess_of_promissory_note: '超额所提诺',
  index_profit_annual: '指数盈利年百分比',
  start_profit_annual: '策略盈利年百分比',
  index_monthly_return_volatility: '指数月收益率波动率',
  start_monthly_return_volatility: '策略月收益率波动率',
  index_maximum_number_of_backtest_repair_days: '指数最大回测天数',
  start_maximum_number_of_backtest_repair_days: '策略最大回测天数',
  excess_maximum_number_of_backtest_repair_days: '超额最大回测天数'
}

const scalarsRows = computed(() => {
  if (!result.value) return []
  return Object.keys(SCALAR_NAME_MAP)
    .filter((key) => result.value[key] !== undefined)
    .map((key) => {
      let value = result.value[key]
      if (key.includes('profit_annual') || key.includes('outperform_year') || key.includes('winning_rate')) {
        value = fmtPct(value)
      } else if (key.includes('maximum_number_of_backtest_repair_days')) {
        value = fmtInt(value)
      } else if (typeof value === 'number') {
        value = fmtNum(value, 6)
      }
      return { key, name: SCALAR_NAME_MAP[key] || '-', value }
    })
})

const sheetResultRows = computed(() => {
  if (!result.value?.sheet_result || typeof result.value.sheet_result !== 'object') return []
  return Object.keys(result.value.sheet_result)
    .sort()
    .map((key) => ({
      key,
      value: typeof result.value.sheet_result[key] === 'object'
        ? JSON.stringify(result.value.sheet_result[key])
        : String(result.value.sheet_result[key] ?? '')
    }))
})

async function loadResult() {
  loading.value = true
  try {
    const res = await getTaskResult(taskId)
    const raw = res.result || res
    if (raw?.calculate_metrics && typeof raw.calculate_metrics === 'object') {
      result.value = { ...raw.calculate_metrics, sheet_result: raw.sheet_result || {} }
    } else {
      result.value = raw
    }
  } catch {
    ElMessage.error('加载回测结果失败')
  } finally {
    loading.value = false
  }
}

async function exportResult() {
  if (!result.value) return
  try {
    const blob = await exportXplResult({
      filename: `result_${taskId}.csv`,
      filename_title: `result_${taskId}`,
      analyze_result: result.value
    })
    const filename = prompt('请输入文件名:', `result_${taskId}.csv`) || `result_${taskId}.csv`
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `result_${taskId}.json`
    link.click()
    URL.revokeObjectURL(url)
  }
}

async function copyRawJson() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2))
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

onMounted(loadResult)
</script>

<style scoped>
.backtest-result-page__summary-grid {
  margin-bottom: 4px;
}

.backtest-result-page__summary-col,
.backtest-result-page__detail-col {
  margin-bottom: 12px;
}

.backtest-result-page__summary-card {
  height: 100%;
  border-width: 1px;
}

.backtest-result-page__summary-card.is-primary {
  border-color: #409eff;
}

.backtest-result-page__summary-card.is-success {
  border-color: #67c23a;
}

.backtest-result-page__summary-card.is-warning {
  border-color: #e6a23c;
}

.backtest-result-page__summary-card.is-danger {
  border-color: #f56c6c;
}

.backtest-result-page__summary-card.is-neutral {
  border-color: #909399;
}

.backtest-result-page__summary-inner {
  text-align: center;
}

.backtest-result-page__summary-value {
  margin: 4px 0;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
}

.backtest-result-page__summary-key {
  color: #94a3b8;
  font-size: 11px;
  word-break: break-all;
}

.backtest-result-page__details {
  margin-top: 8px;
}

.backtest-result-page__tabs :deep(.el-tabs__content) {
  min-height: 520px;
}

.backtest-result-page__card-title {
  margin-bottom: 8px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-result-page__raw-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.backtest-result-page__raw-code {
  max-height: 500px;
  margin: 0;
  overflow: auto;
  font-size: 11px;
}

.text-success {
  color: #16a34a;
}

.text-danger {
  color: #dc2626;
}
</style>
