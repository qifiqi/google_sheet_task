<template>
  <div class="app-page backtest-multi-result-page">
    <PageToolbar
      :eyebrow="displayModelName ? `${displayModelName} Result` : 'Multi-Product Result'"
      :title="pageTitle"
      :description="pageDescription"
    >
      <template #actions>
        <el-tag v-if="displayModelName" size="large" type="primary">{{ displayModelName }}</el-tag>
        <el-button @click="loadResult">刷新</el-button>
        <el-button
          class="page-back-button"
          :disabled="!taskId"
          @click="$router.push({ path: `/backtest-multi/${taskId}`, query: pagingQuery })"
        >返回详情</el-button>
      </template>
    </PageToolbar>

    <div v-if="result" class="panel-note backtest-multi-result-page__meta">
      <span>结果 ID：{{ resultId || '-' }}</span>
      <span>任务 ID：{{ taskId || '-' }}</span>
      <span v-if="allPeriod">区间：{{ allPeriod }}</span>
    </div>

    <!-- 8 个指标摘要卡（静态版 Biz.renderSummary 字段） -->
    <el-row v-if="result" :gutter="12" class="backtest-multi-result-page__summary-grid">
      <el-col
        v-for="card in summaryCards"
        :key="card.key"
        :xs="12"
        :sm="6"
        class="backtest-multi-result-page__summary-col"
      >
        <el-card shadow="never" class="backtest-multi-result-page__summary-card" :class="card.className">
          <div class="backtest-multi-result-page__summary-inner">
            <div class="panel-note">{{ card.label }}</div>
            <div class="backtest-multi-result-page__summary-value">{{ card.value }}</div>
            <div class="backtest-multi-result-page__summary-key">{{ card.key }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="result" shadow="never" class="page-section">
      <div class="section-heading">
        <div>
          <h3 class="section-title section-title--muted">V1 数据明细</h3>
          <div class="panel-note">年度收益、超额指标、比率和原始 JSON 多维查看。</div>
        </div>
        <div class="section-actions">
          <el-button size="small" @click="detailOpen = !detailOpen">{{ detailOpen ? '收起' : '展开' }}明细</el-button>
          <el-button size="small" type="primary" :disabled="!result || exporting" @click="exportV1Details">
            导出并下载
          </el-button>
          <el-button size="small" type="success" plain :disabled="!wordReportPayload || exportingWord" @click="exportWordReport">
            导出 Word
          </el-button>
        </div>
      </div>

      <div v-if="detailOpen" class="backtest-multi-result-page__details">
        <el-tabs v-model="activeDetailTab" tab-position="left" class="backtest-multi-result-page__tabs">
          <el-tab-pane label="年度收益/回撤" name="annual">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="backtest-multi-result-page__detail-col">
                <div class="sub-card">
                  <div class="backtest-multi-result-page__card-title">年度收益率对比</div>
                  <el-table :data="annualCompareRows" stripe border size="small">
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

              <el-col :xs="24" :lg="12" class="backtest-multi-result-page__detail-col">
                <div class="sub-card">
                  <div class="backtest-multi-result-page__card-title">年度最大回撤对比</div>
                  <el-table :data="drawdownCompareRows" stripe border size="small">
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

              <el-col :xs="24" class="backtest-multi-result-page__detail-col">
                <div class="sub-card">
                  <div class="backtest-multi-result-page__card-title">月超额收益百分比</div>
                  <el-table :data="result.monthly_excess_return_percentage || []" stripe border size="small">
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
            <el-table :data="result.excess_returns || []" stripe border size="small" max-height="520">
              <el-table-column prop="year" label="Year" width="80" />
              <el-table-column label="模型收益">
                <template #default="{ row }"><span :class="colorClass(row.start_annualized_return)">{{ fmtPct(row.start_annualized_return) }}</span></template>
              </el-table-column>
              <el-table-column label="指数收益">
                <template #default="{ row }"><span :class="colorClass(row.index_annualized_return)">{{ fmtPct(row.index_annualized_return) }}</span></template>
              </el-table-column>
              <el-table-column label="差值">
                <template #default="{ row }"><span :class="colorClass(row.annualized_return_diff)">{{ fmtPct(row.annualized_return_diff) }}</span></template>
              </el-table-column>
              <el-table-column prop="start_end_date" label="周期" min-width="140" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="月超额收益" name="monthly_excess">
            <el-table :data="result.monthly_excess_returns || []" stripe border size="small" max-height="520">
              <el-table-column prop="year_month" label="月份" width="110" />
              <el-table-column label="指数">
                <template #default="{ row }"><span :class="colorClass(row.index_monthly_return)">{{ fmtPct(row.index_monthly_return) }}</span></template>
              </el-table-column>
              <el-table-column label="模型">
                <template #default="{ row }"><span :class="colorClass(row.start_monthly_return)">{{ fmtPct(row.start_monthly_return) }}</span></template>
              </el-table-column>
              <el-table-column label="月超额收益">
                <template #default="{ row }"><span :class="colorClass(row.monthly_excess_return_diff)">{{ fmtPct(row.monthly_excess_return_diff) }}</span></template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="卡玛比率" name="kama">
            <el-table :data="kamaRows" stripe border size="small" max-height="520">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数Kama"><template #default="{ row }">{{ fmtNum(row.index_kama, 6) }}</template></el-table-column>
              <el-table-column label="模型Kama"><template #default="{ row }">{{ fmtNum(row.model_kama, 6) }}</template></el-table-column>
              <el-table-column label="指数年化"><template #default="{ row }">{{ fmtPct(row.index_annual) }}</template></el-table-column>
              <el-table-column label="模型年化"><template #default="{ row }">{{ fmtPct(row.model_annual) }}</template></el-table-column>
              <el-table-column label="指数回撤"><template #default="{ row }">{{ fmtPct(row.index_dd) }}</template></el-table-column>
              <el-table-column label="模型回撤"><template #default="{ row }">{{ fmtPct(row.model_dd) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="索提诺比例" name="sotino">
            <el-table :data="sortinoRows" stripe border size="small" max-height="520">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数"><template #default="{ row }">{{ fmtNum(row.index_sortino, 6) }}</template></el-table-column>
              <el-table-column label="模型"><template #default="{ row }">{{ fmtNum(row.model_sortino, 6) }}</template></el-table-column>
              <el-table-column label="指数平均月收益"><template #default="{ row }">{{ fmtNum(row.index_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="模型平均月收益"><template #default="{ row }">{{ fmtNum(row.model_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="指数下行标准差"><template #default="{ row }">{{ fmtNum(row.index_downside_std, 6) }}</template></el-table-column>
              <el-table-column label="模型下行标准差"><template #default="{ row }">{{ fmtNum(row.model_downside_std, 6) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="夏普比率" name="sharpe">
            <el-table :data="sharpeRows" stripe border size="small" max-height="520">
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
            <el-table :data="excessMetricsRows" stripe border size="small" max-height="520">
              <el-table-column label="Key" width="220">
                <template #default="{ row }"><code>{{ row.key }}</code></template>
              </el-table-column>
              <el-table-column label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="回测修复天数" name="repair_days">
            <el-table :data="repairDaysRows" stripe border size="small" max-height="520">
              <el-table-column label="Metric" width="140">
                <template #default="{ row }"><code>{{ row.metric }}</code></template>
              </el-table-column>
              <el-table-column label="Value">
                <template #default="{ row }"><span :class="row.colorClass">{{ row.value }}</span></template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="盈利统计" name="profit">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="backtest-multi-result-page__detail-col">
                <div class="sub-card">
                  <div class="backtest-multi-result-page__card-title">盈利年百分比</div>
                  <el-table :data="profitAnnualRow" stripe border size="small">
                    <el-table-column label="指数"><template #default="{ row }">{{ fmtPct(row.index) }}</template></el-table-column>
                    <el-table-column label="模型"><template #default="{ row }">{{ fmtPct(row.model) }}</template></el-table-column>
                  </el-table>
                </div>
              </el-col>

              <el-col :xs="24" :lg="12" class="backtest-multi-result-page__detail-col">
                <el-row :gutter="12">
                  <el-col :xs="24" class="backtest-multi-result-page__detail-col">
                    <div class="sub-card">
                      <div class="backtest-multi-result-page__card-title">指数盈利月占比</div>
                      <el-table :data="result.index_profit_monthly || []" stripe border size="small" max-height="220">
                        <el-table-column prop="year" label="Year" width="80" />
                        <el-table-column label="占比">
                          <template #default="{ row }">{{ fmtPct(row.profit_monthly_percentage) }}</template>
                        </el-table-column>
                      </el-table>
                    </div>
                  </el-col>

                  <el-col :xs="24" class="backtest-multi-result-page__detail-col">
                    <div class="sub-card">
                      <div class="backtest-multi-result-page__card-title">模型盈利月占比</div>
                      <el-table :data="result.start_profit_monthly || []" stripe border size="small" max-height="220">
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
            <el-table :data="scalarsRows" stripe border size="small" max-height="520">
              <el-table-column label="Key" width="300">
                <template #default="{ row }"><code>{{ row.key }}</code></template>
              </el-table-column>
              <el-table-column prop="name" label="Name" width="200" />
              <el-table-column label="Value">
                <template #default="{ row }"><span :class="row.colorClass">{{ row.value }}</span></template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="Sheet 结果" name="sheet_result">
            <el-table :data="sheetResultRows" stripe border size="small" max-height="520">
              <el-table-column label="Key" width="220">
                <template #default="{ row }"><code>{{ row.key }}</code></template>
              </el-table-column>
              <el-table-column prop="value" label="Value" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="每天收益率" name="daily_returns">
            <div class="backtest-multi-result-page__raw-actions">
              <el-button size="small" @click="copyDailyReturns">复制 JSON</el-button>
            </div>
            <el-table v-if="dailyReturnsRows.length" :data="dailyReturnsRows" stripe border size="small" max-height="520">
              <el-table-column prop="date" label="日期" min-width="120" />
              <el-table-column label="指数收益率">
                <template #default="{ row }"><span :class="colorClass(row.index_return)">{{ fmtPct(row.index_return) }}</span></template>
              </el-table-column>
              <el-table-column label="策略收益率">
                <template #default="{ row }"><span :class="colorClass(row.start_return)">{{ fmtPct(row.start_return) }}</span></template>
              </el-table-column>
            </el-table>
            <pre v-else-if="dailyReturnsRawText" class="code-block backtest-multi-result-page__raw-code">{{ dailyReturnsRawText }}</pre>
            <div v-else class="panel-note panel-note--center backtest-multi-result-page__empty-note">暂无数据</div>
          </el-tab-pane>

          <el-tab-pane label="全量 JSON" name="raw">
            <div class="backtest-multi-result-page__raw-actions">
              <el-button size="small" @click="copyRawJson">复制</el-button>
            </div>
            <pre class="code-block backtest-multi-result-page__raw-code">{{ JSON.stringify(result, null, 2) }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>

    <!-- 11 张图表（静态版 renderCharts 系列翻译） -->
    <el-card v-if="result" shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">V1 图表</h3>
      </div>
      <el-row :gutter="12">
        <el-col
          v-for="chart in CHART_LAYOUT"
          :key="chart.key"
          :xs="24"
          :lg="chart.wide ? 24 : 12"
          class="backtest-multi-result-page__chart-col"
        >
          <div class="sub-card">
            <div class="backtest-multi-result-page__card-title">{{ chart.title }}</div>
            <div :style="{ height: chart.wide ? '340px' : '320px' }">
              <canvas :ref="(el) => setChartEl(chart.key, el)"></canvas>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-if="!loading && !result" description="暂无回测结果" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { pickPagingQuery } from '@/utils/pageState'
import { ElMessage } from 'element-plus'
import { getTaskResult, exportWordReportDownload } from '@/api/backtestMulti'
import { exportPerformanceAnalysisResult } from '@/api/performance_analysis'
import { useChartJs } from '@/composables/useChartJs'
import PageToolbar from '@/components/PageToolbar.vue'

const route = useRoute()
const pagingQuery = pickPagingQuery(route.query)
// 路由 :id 是结果 ID（非任务 ID），任务 ID 从 word_report_payload.task_id 推导（静态版同口径）。
const resultId = route.params.id
const loading = ref(false)
const exporting = ref(false)
const exportingWord = ref(false)
const result = ref(null)
const wordReportPayload = ref(null)
const taskId = ref('')
const detailOpen = ref(false)
const activeDetailTab = ref('annual')

const { loadChartJs } = useChartJs()

// ===== 格式化（静态版 Biz.fmtPct/fmtNum/fmtInt 同口径） =====
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

// 静态版 normalizeBacktestResultPayload：calculate_metrics 平铺 + sheet_result 归位。
function normalizeBacktestResultPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null
  }
  if (payload.calculate_metrics && typeof payload.calculate_metrics === 'object') {
    const sheetResult = payload.sheet_result && typeof payload.sheet_result === 'object'
      ? payload.sheet_result
      : Object.fromEntries(Object.entries(payload).filter(([key]) => key !== 'calculate_metrics'))
    return {
      ...payload.calculate_metrics,
      sheet_result: sheetResult,
      model_name: payload.model_name || '',
    }
  }
  return payload
}

// ===== 模型徽章与元信息 =====
const displayModelName = computed(() => {
  const normalized = String(result.value?.model_name || '').trim().toUpperCase()
  return ['C3', 'C4', 'C5', 'C7'].includes(normalized) ? normalized : ''
})

const pageTitle = computed(() => (displayModelName.value ? `${displayModelName.value} 回测结果` : '回测结果'))
const pageDescription = computed(() => (displayModelName.value
  ? `查看并导出当前任务的 ${displayModelName.value} V1 回测分析结果`
  : '查看并导出当前任务的 V1 回测分析结果'))

const allPeriod = computed(() => {
  const list = Array.isArray(result.value?.excess_returns) ? result.value.excess_returns : []
  const all = list.find((item) => String(item?.year).toLowerCase() === 'all')
  return all?.start_end_date || ''
})

// ===== 摘要卡（静态版 Biz.renderSummary 格式化口径） =====
const excessAllValue = computed(() => {
  const entry = Array.isArray(result.value?.excess_returns)
    ? result.value.excess_returns.find((item) => String(item.year) === 'all')
    : null
  return entry ? fmtPct(entry.annualized_return_diff) : '-'
})

const summaryCards = computed(() => [
  { key: 'outperform_year', label: '跑赢年份', value: result.value ? fmtPct(result.value.outperform_year) : '-', className: 'is-primary' },
  { key: 'monthly_excess_volatility', label: '月超额波动率', value: result.value ? fmtNum(result.value.monthly_excess_volatility, 4) : '-', className: 'is-success' },
  { key: 'excess_drawdown_winning_rate', label: '超额回撤胜率', value: result.value ? fmtPct(result.value.excess_drawdown_winning_rate) : '-', className: 'is-warning' },
  { key: 'excess_returns[all]', label: '年超额收益(整体)', value: excessAllValue.value, className: 'is-danger' },
  { key: 'index_profit_annual', label: '指数盈利年%', value: result.value ? fmtPct(result.value.index_profit_annual) : '-', className: 'is-neutral' },
  { key: 'start_profit_annual', label: '模型盈利年%', value: result.value ? fmtPct(result.value.start_profit_annual) : '-', className: 'is-neutral' },
  { key: 'index_monthly_return_volatility', label: '指数月波动率', value: result.value ? fmtNum(result.value.index_monthly_return_volatility, 6) : '-', className: 'is-neutral' },
  { key: 'start_monthly_return_volatility', label: '模型月波动率', value: result.value ? fmtNum(result.value.start_monthly_return_volatility, 6) : '-', className: 'is-neutral' },
])

// ===== 明细表 computed（静态版 result-table.js 字段键名） =====
function idxByYear(list) {
  const map = new Map()
  ;(Array.isArray(list) ? list : []).forEach((item) => {
    if (!item) return
    map.set(String(item.year), item)
  })
  return map
}

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
      diff: modelReturn != null && indexReturn != null ? modelReturn - indexReturn : null,
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
      dates: `${indexItem?.date || '-'} / ${modelItem?.date || '-'}`,
    }
  })
})

const kamaRows = computed(() => {
  if (!result.value) return []
  const indexMap = idxByYear(result.value.index_kama_ratio)
  const modelMap = idxByYear(result.value.start_kama_ratio)
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()]))
    .filter((year) => year !== 'all')
    .sort()
  return years.map((year) => {
    const i = indexMap.get(year)
    const s = modelMap.get(year)
    return {
      year,
      index_kama: i?.kama_ratio,
      model_kama: s?.kama_ratio,
      index_annual: i?.annualized_return,
      model_annual: s?.annualized_return,
      index_dd: i?.drawdown,
      model_dd: s?.drawdown,
    }
  })
})

// 注意拼写：后端键是 index_sortino_ratio / start_sortino_ratio（不是 sotino）。
const sortinoRows = computed(() => {
  if (!result.value) return []
  const indexMap = idxByYear(result.value.index_sortino_ratio)
  const modelMap = idxByYear(result.value.start_sortino_ratio)
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()]))
    .filter((year) => year !== 'all')
    .sort()
  return years.map((year) => {
    const i = indexMap.get(year)
    const s = modelMap.get(year)
    return {
      year,
      index_sortino: i?.sortino_ratio,
      model_sortino: s?.sortino_ratio,
      index_avg_monthly: i?.average_monthly_annualized_return,
      model_avg_monthly: s?.average_monthly_annualized_return,
      index_downside_std: i?.downside_standard_deviation,
      model_downside_std: s?.downside_standard_deviation,
    }
  })
})

// 静态版 formatSharpeKey：all / 近N年 / 年份
function formatSharpeKey(key) {
  const k = String(key ?? '')
  if (!k) return k
  if (k === 'all') return 'all'
  const mPast = k.match(/^past_(\d+)(?:_.*)?$/)
  if (mPast) return `近${Number(mPast[1])}年`
  const mYear = k.match(/^year_\d+_(\d{4})$/)
  if (mYear) return mYear[1]
  return k
}

const sharpeRows = computed(() => {
  if (!result.value) return []
  const indexRatios = result.value.index_sharpe_ratios || {}
  const modelRatios = result.value.start_sharpe_ratios || {}
  const keys = Array.from(new Set([...Object.keys(indexRatios), ...Object.keys(modelRatios)])).sort()
  return keys.map((key) => {
    const indexItem = indexRatios[key]
    const modelItem = modelRatios[key]
    const base = indexItem && typeof indexItem === 'object' ? indexItem : (modelItem && typeof modelItem === 'object' ? modelItem : null)
    if (!base) return null
    return {
      period: formatSharpeKey(key),
      index_sharpe: indexItem?.sharpe_ratio,
      model_sharpe: modelItem?.sharpe_ratio,
      index_avg_monthly: indexItem?.avg_monthly_return,
      model_avg_monthly: modelItem?.avg_monthly_return,
      index_monthly_std: indexItem?.monthly_std_dev,
      model_monthly_std: modelItem?.monthly_std_dev,
      index_annual_std: indexItem?.annual_std_dev,
      model_annual_std: modelItem?.annual_std_dev,
      start_date: base?.start_date,
      end_date: base?.end_date,
    }
  }).filter(Boolean)
})

// 注意拼写：后端键是 excess_sharpe / excess_sortino。
const excessMetricsRows = computed(() => {
  if (!result.value) return []
  return [
    { key: 'excess_sharpe', value: result.value.excess_sharpe === undefined ? '-' : fmtNum(result.value.excess_sharpe, 6) },
    { key: 'excess_sortino', value: result.value.excess_sortino === undefined ? '-' : fmtNum(result.value.excess_sortino, 6) },
  ]
})

const repairDaysRows = computed(() => {
  if (!result.value) return []
  return [
    ['index', result.value.index_maximum_number_of_backtest_repair_days],
    ['start', result.value.start_maximum_number_of_backtest_repair_days],
    ['excess', result.value.excess_maximum_number_of_backtest_repair_days],
  ]
    .filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)))
    .map(([metric, value]) => ({
      metric,
      value: fmtInt(value),
      colorClass: metric === 'excess' ? colorClass(value) : '',
    }))
})

const profitAnnualRow = computed(() => {
  if (!result.value) return []
  return [{ index: result.value.index_profit_annual, model: result.value.start_profit_annual }]
})

const SCALAR_NAME_MAP = {
  outperform_year: '跑赢年份',
  monthly_excess_volatility: '月超额波动率',
  excess_drawdown_winning_rate: '超额回撤胜率',
  excess_sharpe: '超额夏普',
  excess_sortino: '超额索提诺',
  index_profit_annual: '指数盈利年百分比',
  start_profit_annual: '策略盈利年百分比',
  index_monthly_return_volatility: '指数月收益率波动率',
  start_monthly_return_volatility: '策略月收益率波动率',
  index_maximum_number_of_backtest_repair_days: '指数最大回测天数',
  start_maximum_number_of_backtest_repair_days: '策略最大回测天数',
  excess_maximum_number_of_backtest_repair_days: '超额最大回测天数',
}

const scalarsRows = computed(() => {
  if (!result.value) return []
  return Object.keys(SCALAR_NAME_MAP)
    .filter((key) => result.value[key] !== undefined)
    .map((key) => {
      let value = result.value[key]
      let colorClassValue = ''
      if (key.includes('profit_annual') || key.includes('outperform_year') || key.includes('winning_rate')) {
        value = fmtPct(value)
        colorClassValue = colorClass(result.value[key])
      } else if (key.includes('maximum_number_of_backtest_repair_days')) {
        value = fmtInt(value)
      } else if (typeof value === 'number') {
        value = fmtNum(value, 6)
      }
      return { key, name: SCALAR_NAME_MAP[key] || '-', value, colorClass: colorClassValue }
    })
})

const sheetResultRows = computed(() => {
  const sheetResult = result.value?.sheet_result
  if (!sheetResult || typeof sheetResult !== 'object' || Array.isArray(sheetResult)) return []
  return Object.keys(sheetResult)
    .sort()
    .map((key) => ({
      key,
      value: typeof sheetResult[key] === 'object' && sheetResult[key] !== null
        ? JSON.stringify(sheetResult[key], null, 2)
        : String(sheetResult[key] ?? ''),
    }))
})

// 每天收益率（静态版 renderTabDailyReturns）：对象/数组/字符串三种形态都兼容。
const dailyReturnsRawText = ref('')
const dailyReturnsRows = computed(() => {
  if (!result.value) return []
  const raw = result.value.daily_returns
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const dates = Array.isArray(raw.dates) ? raw.dates : []
    const indexReturns = Array.isArray(raw.index_returns) ? raw.index_returns : []
    const startReturns = Array.isArray(raw.start_returns) ? raw.start_returns : []
    const maxLength = Math.max(dates.length, indexReturns.length, startReturns.length)
    const rows = []
    for (let i = 0; i < maxLength; i += 1) {
      rows.push({
        date: dates[i] ?? '-',
        index_return: indexReturns[i],
        start_return: startReturns[i],
      })
    }
    return rows
  }
  if (Array.isArray(raw)) {
    return raw.map((item) => ({
      date: item?.date ?? item?.stock_date ?? '-',
      index_return: item?.index_return ?? item?.indexReturns ?? null,
      start_return: item?.start_return ?? item?.strategy_return ?? null,
    }))
  }
  return []
})

function buildDailyReturnsJsonText(raw) {
  if (raw && typeof raw === 'object') return JSON.stringify(raw, null, 2)
  if (typeof raw === 'string') return raw
  if (raw !== null && raw !== undefined) return String(raw)
  return ''
}

// ===== 数据加载 =====
async function loadResult() {
  loading.value = true
  try {
    const data = await getTaskResult(resultId)
    const normalized = normalizeBacktestResultPayload(data?.result)
    if (!normalized) {
      result.value = null
      ElMessage.warning('结果数据为空')
      return
    }
    result.value = normalized
    wordReportPayload.value = data?.word_report_payload || null
    taskId.value = data?.word_report_payload?.task_id || ''
    dailyReturnsRawText.value = buildDailyReturnsJsonText(normalized.daily_returns)
    await nextTick()
    await renderCharts(normalized)
  } catch (error) {
    result.value = null
    ElMessage.error(`加载结果失败：${error.message || '未知错误'}`)
  } finally {
    loading.value = false
  }
}

// ===== 导出（静态版 exportV1Details / exportWordReport） =====
async function exportV1Details() {
  if (!result.value) {
    ElMessage.warning('请先完成分析再导出')
    return
  }
  exporting.value = true
  try {
    const exportBaseName = `backtest_result_${resultId}`
    const defaultFilename = `${exportBaseName}_details.csv`
    const resp = await exportPerformanceAnalysisResult({
      filename: defaultFilename,
      filename_title: exportBaseName,
      model_name: result.value.model_name || 'C3',
      analyze_result: result.value,
    })
    // 与静态版一致：允许用户确认/修改文件名
    const userFilename = prompt('请输入文件名:', defaultFilename)
    if (userFilename === null) {
      ElMessage.info('用户取消了保存操作')
      return
    }
    const finalFilename = userFilename.trim() || defaultFilename
    const url = URL.createObjectURL(resp)
    const link = document.createElement('a')
    link.href = url
    link.download = finalFilename.endsWith('.csv') ? finalFilename : `${finalFilename}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success(`开始下载：${finalFilename}`)
  } catch (error) {
    ElMessage.error(`导出失败：${error.message || '未知错误'}`)
  } finally {
    exporting.value = false
  }
}

async function exportWordReport() {
  if (!wordReportPayload.value) {
    ElMessage.warning('当前参数方案缺少完整的多品收益序列')
    return
  }
  exportingWord.value = true
  try {
    const { blob, filename } = await exportWordReportDownload(wordReportPayload.value, 'RPT-M.docx')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('Word 报告已下载')
  } catch (error) {
    ElMessage.error(`Word 导出失败：${error.message || '未知错误'}`)
  } finally {
    exportingWord.value = false
  }
}

// ===== 复制 =====
async function copyRawJson() {
  const text = result.value ? JSON.stringify(result.value, null, 2) : ''
  if (!text) {
    ElMessage.warning('暂无可复制内容')
    return
  }
  try {
    await writeClipboardText(text)
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function copyDailyReturns() {
  const text = dailyReturnsRawText.value
  if (!text) {
    ElMessage.warning('暂无可复制内容')
    return
  }
  try {
    await writeClipboardText(text)
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  textarea.remove()
  if (!ok) throw new Error('copy failed')
}

// ===== 图表（静态版 renderCharts 系列逐图翻译，Chart.js 经 useChartJs CDN 加载） =====
const CHART_LAYOUT = [
  { key: 'annual-returns', title: '年度收益率（指数 vs 模型）' },
  { key: 'excess-annual', title: '年超额收益（模型 - 指数）' },
  { key: 'annual-drawdown', title: '年度最大回撤（指数 vs 模型）' },
  { key: 'kama', title: '卡玛比率（指数 vs 模型）' },
  { key: 'sotino', title: '索提诺比例（指数 vs 模型）' },
  { key: 'monthly-vol', title: '月收益率波动率（指数 vs 模型）' },
  { key: 'monthly-excess-returns', title: '月超额收益（模型 - 指数）', wide: true },
  { key: 'sharpe-compare', title: '夏普比率对比（all / year_* / past_*）', wide: true },
  { key: 'excess-metrics', title: '超额指标（夏普 / 索提诺）' },
  { key: 'repair-days', title: '最大回测修复天数（index / start / excess）' },
  { key: 'profit-monthly', title: '盈利月百分比（指数 vs 模型）', wide: true },
]

const chartEls = {}
const charts = {}

function setChartEl(key, el) {
  chartEls[key] = el
}

function destroyChart(key) {
  const chart = charts[key]
  if (chart) {
    try {
      chart.destroy()
    } catch {
      // 忽略销毁异常
    }
  }
  charts[key] = null
}

function destroyAllCharts() {
  Object.keys(charts).forEach(destroyChart)
}

function buildLineChart(Chart, key, labels, datasets, yTitle, xTitle = 'Year') {
  const el = chartEls[key]
  if (!el) return
  destroyChart(key)
  const singlePointMode = labels.length <= 1
  const normalizedDatasets = datasets.map((ds) => ({
    ...ds,
    fill: singlePointMode ? false : ds.fill,
    tension: singlePointMode ? 0 : (ds.tension ?? 0.1),
    pointRadius: singlePointMode ? 0 : (ds.pointRadius ?? 3),
    pointHoverRadius: singlePointMode ? 0 : (ds.pointHoverRadius ?? 5),
    borderWidth: ds.borderWidth ?? 2,
  }))
  charts[key] = new Chart(el, {
    type: singlePointMode ? 'bar' : 'line',
    data: { labels, datasets: normalizedDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: { title: { display: true, text: yTitle }, grace: '8%' },
        x: { title: { display: true, text: xTitle } },
      },
    },
  })
}

function buildBarChart(Chart, key, labels, datasets, yTitle, xOptions) {
  const el = chartEls[key]
  if (!el) return
  destroyChart(key)
  charts[key] = new Chart(el, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { title: { display: true, text: yTitle } },
        x: xOptions ? { ticks: xOptions } : { title: { display: true, text: 'Year' } },
      },
    },
  })
}

// 静态版 normalizeYearSeries：去掉 all，年份序输出 {labels, values, map}
function normalizeYearSeries(list, valueKey) {
  const map = new Map()
  if (Array.isArray(list)) {
    list.forEach((item) => {
      if (!item) return
      const year = String(item.year)
      if (year === 'all') return
      map.set(year, item[valueKey])
    })
  }
  const labels = Array.from(map.keys()).sort()
  const values = labels.map((year) => map.get(year))
  return { labels, values, map }
}

function profitMonthlySeries(list) {
  const map = new Map()
  if (Array.isArray(list)) {
    list.forEach((item) => {
      if (!item) return
      map.set(String(item.year), item.profit_monthly_percentage)
    })
  }
  return map
}

function repairDaysValues(r) {
  return [
    ['index', r.index_maximum_number_of_backtest_repair_days],
    ['start', r.start_maximum_number_of_backtest_repair_days],
    ['excess', r.excess_maximum_number_of_backtest_repair_days],
  ].filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)))
}

function sharpeEntriesToSeries(obj) {
  const arr = []
  if (!obj || typeof obj !== 'object') return arr
  Object.entries(obj).forEach(([key, value]) => {
    if (!value || typeof value !== 'object') return
    if (value.sharpe_ratio === undefined || value.sharpe_ratio === null) return
    arr.push({ key: formatSharpeKey(key), sharpe: value.sharpe_ratio })
  })
  arr.sort((a, b) => {
    if (a.key === 'all' && b.key !== 'all') return -1
    if (b.key === 'all' && a.key !== 'all') return 1
    return a.key.localeCompare(b.key)
  })
  return arr
}

async function renderCharts(r) {
  try {
    const Chart = await loadChartJs()
    if (!Chart) return

    // 1. 年度收益率
    const idxAnnual = normalizeYearSeries(r.index_returns_rate, 'annual_return')
    const stAnnual = normalizeYearSeries(r.start_returns_rate, 'annual_return')
    const labelsAnnual = Array.from(new Set([...idxAnnual.labels, ...stAnnual.labels])).sort()
    buildLineChart(Chart, 'annual-returns', labelsAnnual, [
      {
        label: '指数年度收益(%)',
        data: labelsAnnual.map((y) => {
          const v = idxAnnual.map.get(y)
          return v === null || v === undefined ? null : v * 100
        }),
        borderColor: '#0d6efd',
        backgroundColor: 'rgba(13,110,253,0.08)',
        tension: 0.1,
        fill: true,
      },
      {
        label: '模型年度收益(%)',
        data: labelsAnnual.map((y) => {
          const v = stAnnual.map.get(y)
          return v === null || v === undefined ? null : v * 100
        }),
        borderColor: '#198754',
        backgroundColor: 'rgba(25,135,84,0.08)',
        tension: 0.1,
        fill: true,
      },
    ], 'Return (%)')

    // 2. 年超额收益
    const exMap = new Map()
    if (Array.isArray(r.excess_returns)) {
      r.excess_returns.forEach((item) => {
        const y = String(item.year)
        if (y === 'all') return
        exMap.set(y, item.annualized_return_diff)
      })
    }
    const exLabels = Array.from(exMap.keys()).sort()
    const exVals = exLabels.map((y) => (exMap.get(y) ?? 0) * 100)
    buildBarChart(Chart, 'excess-annual', exLabels, [{
      label: '年超额收益 (%)',
      data: exVals,
      backgroundColor: exVals.map((v) => (v >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)')),
      borderColor: exVals.map((v) => (v >= 0 ? '#198754' : '#dc3545')),
      borderWidth: 1,
    }], 'Excess Return (%)')

    // 3. 年度最大回撤
    const idxDd = normalizeYearSeries(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
    const stDd = normalizeYearSeries(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
    const ddLabels = Array.from(new Set([...idxDd.labels, ...stDd.labels])).sort()
    buildLineChart(Chart, 'annual-drawdown', ddLabels, [
      {
        label: '指数最大回撤 (%)',
        data: ddLabels.map((y) => {
          const v = idxDd.map.get(y)
          return v === null || v === undefined ? null : v * 100
        }),
        borderColor: '#dc3545',
        backgroundColor: 'rgba(220,53,69,0.08)',
        tension: 0.1,
        fill: true,
      },
      {
        label: '模型最大回撤 (%)',
        data: ddLabels.map((y) => {
          const v = stDd.map.get(y)
          return v === null || v === undefined ? null : v * 100
        }),
        borderColor: '#fd7e14',
        backgroundColor: 'rgba(253,126,20,0.08)',
        tension: 0.1,
        fill: true,
      },
    ], 'Drawdown (%)')

    // 4. 卡玛
    const kamaIdx = normalizeYearSeries(r.index_kama_ratio, 'kama_ratio')
    const kamaSt = normalizeYearSeries(r.start_kama_ratio, 'kama_ratio')
    const kamaLabels = Array.from(new Set([...kamaIdx.labels, ...kamaSt.labels])).sort()
    buildLineChart(Chart, 'kama', kamaLabels, [
      {
        label: '指数Kama',
        data: kamaLabels.map((y) => kamaIdx.map.get(y) ?? null),
        borderColor: '#0dcaf0',
        backgroundColor: 'rgba(13,202,240,0.08)',
        tension: 0.1,
        fill: true,
      },
      {
        label: '模型Kama',
        data: kamaLabels.map((y) => kamaSt.map.get(y) ?? null),
        borderColor: '#6610f2',
        backgroundColor: 'rgba(102,16,242,0.08)',
        tension: 0.1,
        fill: true,
      },
    ], 'Kama Ratio')

    // 5. 索提诺
    const sotIdx = normalizeYearSeries(r.index_sortino_ratio, 'sortino_ratio')
    const sotSt = normalizeYearSeries(r.start_sortino_ratio, 'sortino_ratio')
    const sotLabels = Array.from(new Set([...sotIdx.labels, ...sotSt.labels])).sort()
    buildLineChart(Chart, 'sotino', sotLabels, [
      {
        label: '指数Sotino',
        data: sotLabels.map((y) => sotIdx.map.get(y) ?? null),
        borderColor: '#20c997',
        backgroundColor: 'rgba(32,201,151,0.08)',
        tension: 0.1,
        fill: true,
      },
      {
        label: '模型Sotino',
        data: sotLabels.map((y) => sotSt.map.get(y) ?? null),
        borderColor: '#d63384',
        backgroundColor: 'rgba(214,51,132,0.08)',
        tension: 0.1,
        fill: true,
      },
    ], 'Sotino Ratio')

    // 6. 月收益率波动率
    const volEl = chartEls['monthly-vol']
    if (volEl) {
      destroyChart('monthly-vol')
      charts['monthly-vol'] = new Chart(volEl, {
        type: 'bar',
        data: {
          labels: ['指数', '模型'],
          datasets: [{
            label: '月收益率波动率',
            data: [
              r.index_monthly_return_volatility !== undefined ? r.index_monthly_return_volatility : null,
              r.start_monthly_return_volatility !== undefined ? r.start_monthly_return_volatility : null,
            ],
            backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'],
            borderColor: ['#0d6efd', '#198754'],
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: 'Volatility' } } },
        },
      })
    }

    // 7. 月超额收益
    const monthlyList = Array.isArray(r.monthly_excess_returns) ? r.monthly_excess_returns : []
    const sortedMonthly = monthlyList
      .filter((x) => x && x.year_month)
      .slice()
      .sort((a, b) => String(a.year_month).localeCompare(String(b.year_month)))
    const mExLabels = sortedMonthly.map((x) => String(x.year_month))
    const mExVals = sortedMonthly.map((x) => (x.monthly_excess_return_diff ?? null))
    const mExValsPct = mExVals.map((v) => (v === null ? null : Number(v) * 100))
    const monthlyEl = chartEls['monthly-excess-returns']
    if (monthlyEl) {
      destroyChart('monthly-excess-returns')
      charts['monthly-excess-returns'] = new Chart(monthlyEl, {
        type: 'bar',
        data: {
          labels: mExLabels,
          datasets: [{
            label: '月超额收益 (%)',
            data: mExValsPct,
            backgroundColor: mExVals.map((v) => ((v ?? 0) >= 0 ? 'rgba(25,135,84,0.55)' : 'rgba(220,53,69,0.55)')),
            borderColor: mExVals.map((v) => ((v ?? 0) >= 0 ? '#198754' : '#dc3545')),
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { title: { display: true, text: 'Excess Return (%)' } },
            x: { ticks: { autoSkip: true, maxRotation: 60, minRotation: 0 } },
          },
        },
      })
    }

    // 8. 夏普对比
    const idxSeries = sharpeEntriesToSeries(r.index_sharpe_ratios)
    const stSeries = sharpeEntriesToSeries(r.start_sharpe_ratios)
    const sharpeLabels = Array.from(new Set([...idxSeries.map((x) => x.key), ...stSeries.map((x) => x.key)]))
      .sort((a, b) => {
        if (a === 'all' && b !== 'all') return -1
        if (b === 'all' && a !== 'all') return 1
        return String(a).localeCompare(String(b))
      })
    const idxSharpeMap = new Map(idxSeries.map((x) => [x.key, x.sharpe]))
    const stSharpeMap = new Map(stSeries.map((x) => [x.key, x.sharpe]))
    buildBarChart(Chart, 'sharpe-compare', sharpeLabels, [
      {
        label: '指数夏普',
        data: sharpeLabels.map((k) => idxSharpeMap.get(k) ?? null),
        backgroundColor: 'rgba(13,110,253,0.45)',
        borderColor: '#0d6efd',
        borderWidth: 1,
      },
      {
        label: '模型夏普',
        data: sharpeLabels.map((k) => stSharpeMap.get(k) ?? null),
        backgroundColor: 'rgba(25,135,84,0.45)',
        borderColor: '#198754',
        borderWidth: 1,
      },
    ], 'Sharpe Ratio', { autoSkip: false, maxRotation: 60, minRotation: 20 })

    // 9. 超额指标
    const excessEl = chartEls['excess-metrics']
    if (excessEl) {
      destroyChart('excess-metrics')
      charts['excess-metrics'] = new Chart(excessEl, {
        type: 'bar',
        data: {
          labels: ['excess_sharpe', 'excess_sortino'],
          datasets: [{
            label: 'Value',
            data: [r.excess_sharpe ?? null, r.excess_sortino ?? null],
            backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'],
            borderColor: ['#0d6efd', '#198754'],
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: 'Metric Value' } } },
        },
      })
    }

    // 10. 修复天数
    const repairRows = repairDaysValues(r)
    const repairEl = chartEls['repair-days']
    if (repairEl && repairRows.length) {
      destroyChart('repair-days')
      charts['repair-days'] = new Chart(repairEl, {
        type: 'bar',
        data: {
          labels: repairRows.map(([key]) => key),
          datasets: [{
            label: 'Repair Days',
            data: repairRows.map(([, value]) => Number(value)),
            backgroundColor: ['rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)', 'rgba(253,126,20,0.45)'].slice(0, repairRows.length),
            borderColor: ['#0d6efd', '#198754', '#fd7e14'].slice(0, repairRows.length),
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: 'Days' } } },
        },
      })
    }

    // 11. 盈利月占比（静态版固定 line 类型 + y 轴 0~100）
    const idxProfitMap = profitMonthlySeries(r.index_profit_monthly)
    const stProfitMap = profitMonthlySeries(r.start_profit_monthly)
    const profitLabels = Array.from(new Set([...idxProfitMap.keys(), ...stProfitMap.keys()])).sort()
    const profitEl = chartEls['profit-monthly']
    if (profitEl) {
      destroyChart('profit-monthly')
      charts['profit-monthly'] = new Chart(profitEl, {
        type: 'line',
        data: {
          labels: profitLabels,
          datasets: [
            {
              label: '指数盈利月占比 (%)',
              data: profitLabels.map((y) => {
                const v = idxProfitMap.get(y)
                return v === null || v === undefined ? null : v * 100
              }),
              borderColor: '#0d6efd',
              backgroundColor: 'rgba(13,110,253,0.08)',
              tension: 0.1,
              fill: true,
            },
            {
              label: '模型盈利月占比 (%)',
              data: profitLabels.map((y) => {
                const v = stProfitMap.get(y)
                return v === null || v === undefined ? null : v * 100
              }),
              borderColor: '#198754',
              backgroundColor: 'rgba(25,135,84,0.08)',
              tension: 0.1,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { title: { display: true, text: 'Percentage (%)' }, beginAtZero: true, max: 100 },
          },
        },
      })
    }
  } catch {
    // CDN 加载失败时跳过图表，不影响表格展示
  }
}

onMounted(loadResult)

onBeforeUnmount(() => {
  destroyAllCharts()
})
</script>

<style scoped>
.backtest-multi-result-page__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 8px;
}

.backtest-multi-result-page__summary-grid {
  margin-bottom: 4px;
}

.backtest-multi-result-page__summary-col,
.backtest-multi-result-page__detail-col,
.backtest-multi-result-page__chart-col {
  margin-bottom: 12px;
}

.backtest-multi-result-page__summary-card {
  height: 100%;
  border-width: 1px;
}

.backtest-multi-result-page__summary-card.is-primary {
  border-color: #409eff;
}

.backtest-multi-result-page__summary-card.is-success {
  border-color: #67c23a;
}

.backtest-multi-result-page__summary-card.is-warning {
  border-color: #e6a23c;
}

.backtest-multi-result-page__summary-card.is-danger {
  border-color: #f56c6c;
}

.backtest-multi-result-page__summary-card.is-neutral {
  border-color: #909399;
}

.backtest-multi-result-page__summary-inner {
  text-align: center;
}

.backtest-multi-result-page__summary-value {
  margin: 4px 0;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
}

.backtest-multi-result-page__summary-key {
  color: #94a3b8;
  font-size: 11px;
  word-break: break-all;
}

.backtest-multi-result-page__details {
  margin-top: 8px;
}

.backtest-multi-result-page__tabs :deep(.el-tabs__content) {
  min-height: 520px;
}

.backtest-multi-result-page__card-title {
  margin-bottom: 8px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-result-page__raw-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.backtest-multi-result-page__raw-code {
  max-height: 520px;
  margin: 0;
  overflow: auto;
  font-size: 11px;
}

.backtest-multi-result-page__empty-note {
  padding: 32px 0;
}

.text-success {
  color: #16a34a;
}

.text-danger {
  color: #dc2626;
}
</style>
