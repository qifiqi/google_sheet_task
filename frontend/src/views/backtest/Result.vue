<template>
  <div class="app-page backtest-result-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Result</div>
        <h2 class="page-title">
          {{ pageTitle }}
          <el-tag v-if="displayModelName" type="primary" size="large">{{ displayModelName }}</el-tag>
        </h2>
        <p class="page-description">{{ pageDescription }}</p>
        <div v-if="result" class="backtest-result-page__meta">
          <span>结果 <span class="font-mono">{{ resultId || '-' }}</span></span>
          <span>任务 <span class="font-mono">{{ taskId || '-' }}</span></span>
          <span v-if="allPeriod">{{ allPeriod }}</span>
        </div>
      </div>
      <div class="page-toolbar__actions">
        <el-button @click="loadResult">刷新</el-button>
        <el-button type="success" plain :disabled="!wordReportPayload" :loading="exportingWord" @click="exportWordReport">
          导出 Word 报告
        </el-button>
        <el-button type="primary" plain @click="router.push({ path: `/backtest/${resultId}/result-export-preview`, query: pagingQuery })">导出预览</el-button>
        <el-button
          class="page-back-button"
          :disabled="!taskId"
          @click="router.push({ path: `/backtest/${taskId}`, query: pagingQuery })"
        >返回</el-button>
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
            <el-button size="small" type="primary" :disabled="!result || exportingCsv" @click="exportResult">
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

            <el-tab-pane label="索提诺比率" name="sotino">
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

      <el-card v-if="result" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">V1 图表</h3>
        </div>
        <el-row :gutter="12">
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">年度收益率（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartAnnualReturns"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">年超额收益（模型 - 指数）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartExcessAnnual"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">年度最大回撤（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartAnnualDrawdown"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">卡玛比率（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartKama"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">索提诺比例（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartSotino"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">月收益率波动率（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartMonthlyVol"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="24" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">月超额收益（模型 - 指数）</div>
              <div class="backtest-result-page__chart-box backtest-result-page__chart-box--tall"><canvas ref="chartMonthlyExcessReturns"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="24" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">夏普比率对比（all / year_* / past_*）</div>
              <div class="backtest-result-page__chart-box backtest-result-page__chart-box--tall"><canvas ref="chartSharpeCompare"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">超额指标（夏普 / 索提诺）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartExcessMetrics"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="12" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">最大回测修复天数（index / start / excess）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartRepairDays"></canvas></div>
            </div>
          </el-col>
          <el-col :lg="24" :xs="24" class="backtest-result-page__chart-col">
            <div class="sub-card">
              <div class="backtest-result-page__card-title">盈利月百分比（指数 vs 模型）</div>
              <div class="backtest-result-page__chart-box"><canvas ref="chartProfitMonthly"></canvas></div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <el-empty v-if="!loading && !result" description="暂无回测结果" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { pickPagingQuery } from '@/utils/pageState'
import { ElMessage } from 'element-plus'
import { getTaskResult, exportBacktestResultCsv, exportBacktestWordReport } from '@/api/backtest'
import { useChartJs } from '@/composables/useChartJs'

const route = useRoute()
const router = useRouter()
const pagingQuery = pickPagingQuery(route.query)
// 路由 :id 为结果 ID（详情页「查看结果」带 task_result_id 跳入，与静态版 /result/{resultId} 一致）
const resultId = route.params.id
const loading = ref(false)
const result = ref(null)
const detailOpen = ref(false)
const activeDetailTab = ref('annual')
const wordReportPayload = ref(null)
const taskId = ref('')
const exportingCsv = ref(false)
const exportingWord = ref(false)
let exportBaseName = ''

const { loadChartJs } = useChartJs()

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

// ---------- 模型身份（badge / 标题 / meta，翻译自静态 renderModelIdentity） ----------
const displayModelName = computed(() => {
  const normalized = String(result.value?.model_name || '').trim().toUpperCase()
  return ['C3', 'C4', 'C5', 'C7'].includes(normalized) ? normalized : ''
})
const pageTitle = computed(() => (displayModelName.value ? `${displayModelName.value} 回测结果` : '回测结果'))
const pageDescription = computed(() => (
  displayModelName.value
    ? `查看并导出当前任务的 ${displayModelName.value} V1 回测分析结果`
    : '查看并导出当前任务的 V1 回测分析结果'
))
const allPeriod = computed(() => {
  const entry = Array.isArray(result.value?.excess_returns)
    ? result.value.excess_returns.find((item) => String(item?.year).toLowerCase() === 'all')
    : null
  return entry?.start_end_date || ''
})

function updateDocumentTitle() {
  document.title = displayModelName.value ? `${displayModelName.value} 回测结果` : '回测结果'
}

// ---------- 汇总卡片 ----------
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

// ---------- 表格数据 ----------
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
  ;(result.value.index_sortino_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') indexMap.set(String(item.year), item)
  })
  ;(result.value.start_sortino_ratio || []).forEach((item) => {
    if (String(item.year) !== 'all') modelMap.set(String(item.year), item)
  })
  const years = Array.from(new Set([...indexMap.keys(), ...modelMap.keys()])).sort()
  return years.map((year) => {
    const indexItem = indexMap.get(year)
    const modelItem = modelMap.get(year)
    return {
      year,
      index_sotino: indexItem?.sortino_ratio,
      model_sotino: modelItem?.sortino_ratio,
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
    { key: 'excess_sharpe', value: fmtNum(result.value.excess_sharpe, 6) },
    { key: 'excess_sortino', value: fmtNum(result.value.excess_sortino, 6) }
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

// 关键标量键名与后端输出一致（excess_sharpe / excess_sortino，参照 base.py 规格表）
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

// ---------- 结果载荷规范化（翻译自 Biz.normalizeBacktestResultPayload） ----------
function normalizeResultPayload(payload) {
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
      stock_code: payload.stock_code,
    }
  }
  return payload
}

// ---------- 导出基名（翻译自静态 buildExportBaseName：模型-股票-起止年） ----------
function buildExportBaseName(resultData) {
  const modelName = String(resultData?.model_name || '').trim().toUpperCase()
  const stockCode = String(resultData?.stock_code || '').trim().toUpperCase()
  const allPeriodEntry = Array.isArray(resultData?.excess_returns)
    ? resultData.excess_returns.find((item) => String(item?.year).toLowerCase() === 'all')
    : null
  const years = String(allPeriodEntry?.start_end_date || '').match(/(?:19|20)\d{2}/g) || []

  if (!modelName || !stockCode || !years.length) {
    return `backtest_result_${resultId}`
  }

  const latestYear = Math.max(...years.map(Number))
  const earliestYear = Math.min(...years.map(Number))
  const period = latestYear === earliestYear
    ? String(latestYear)
    : `${latestYear}-${earliestYear}`
  return `${modelName}-${stockCode}-${period}`
}

// ---------- 加载 ----------
async function loadResult() {
  loading.value = true
  try {
    const data = await getTaskResult(encodeURIComponent(resultId))
    const resultData = normalizeResultPayload(data && data.result)
    if (!resultData) {
      result.value = null
      wordReportPayload.value = null
      ElMessage.warning('结果数据为空')
      return
    }

    result.value = resultData
    wordReportPayload.value = (data && data.word_report_payload) || null
    // 静态化（03 §4.3）：task_id 改从结果接口响应推导
    taskId.value = (wordReportPayload.value && wordReportPayload.value.task_id) || ''
    exportBaseName = buildExportBaseName(resultData)
    updateDocumentTitle()
    await nextTick()
    await renderCharts(resultData)
    ElMessage.success('结果加载完成')
  } catch (error) {
    result.value = null
    ElMessage.error(`加载结果失败：${error.message || '未知错误'}`)
  } finally {
    loading.value = false
  }
}

// ---------- 导出 ----------
async function exportResult() {
  if (!result.value || exportingCsv.value) return
  exportingCsv.value = true
  try {
    const blob = await exportBacktestResultCsv(encodeURIComponent(resultId))
    // 文件名照静态 exportV1Details：基名来自结果数据（模型-股票-起止年），基名为回退名时加 _details 后缀
    const filename = exportBaseName.startsWith('backtest_result_')
      ? `${exportBaseName}_details.csv`
      : `${exportBaseName}.csv`
    downloadBlob(blob, filename.endsWith('.csv') ? filename : `${filename}.csv`)
    ElMessage.success(`开始下载：${filename}`)
  } catch (error) {
    ElMessage.error(`导出失败：${error.message || '未知错误'}`)
  } finally {
    exportingCsv.value = false
  }
}

async function exportWordReport() {
  if (!wordReportPayload.value || exportingWord.value) {
    if (!wordReportPayload.value) {
      ElMessage.warning('当前结果没有可导出的收益序列')
    }
    return
  }
  exportingWord.value = true
  try {
    const { blob, filename } = await exportBacktestWordReport(wordReportPayload.value)
    downloadBlob(blob, filename)
    ElMessage.success('Word 报告已下载')
  } catch (error) {
    ElMessage.error(`Word 导出失败：${error.message || '未知错误'}`)
  } finally {
    exportingWord.value = false
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function copyRawJson() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2))
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

// ---------- 图表（翻译自静态 result.js renderCharts 及各 build*Chart） ----------
const chartAnnualReturns = ref(null)
const chartExcessAnnual = ref(null)
const chartAnnualDrawdown = ref(null)
const chartKama = ref(null)
const chartSotino = ref(null)
const chartMonthlyVol = ref(null)
const chartMonthlyExcessReturns = ref(null)
const chartSharpeCompare = ref(null)
const chartExcessMetrics = ref(null)
const chartRepairDays = ref(null)
const chartProfitMonthly = ref(null)

const chartInstances = {}

function destroyChart(key) {
  const chart = chartInstances[key]
  if (chart) {
    try {
      chart.destroy()
    } catch {
      // Chart.js 实例可能已被外部销毁
    }
  }
  chartInstances[key] = null
}

function destroyAllCharts() {
  Object.keys(chartInstances).forEach(destroyChart)
}

function baseOptions(yTitle, extraScales = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      y: { title: { display: true, text: yTitle }, grace: '8%', ...extraScales.y },
      x: { title: { display: true, text: 'Year' }, ...extraScales.x },
    },
  }
}

function buildLineChart(canvasRef, key, labels, datasets, yTitle) {
  const el = canvasRef.value
  if (!el) return
  destroyChart(key)
  const singlePointMode = labels.length <= 1
  const chartType = singlePointMode ? 'bar' : 'line'
  const normalizedDatasets = datasets.map((ds) => ({
    ...ds,
    fill: singlePointMode ? false : ds.fill,
    tension: singlePointMode ? 0 : (ds.tension ?? 0.1),
    pointRadius: singlePointMode ? 0 : (ds.pointRadius ?? 3),
    pointHoverRadius: singlePointMode ? 0 : (ds.pointHoverRadius ?? 5),
    borderWidth: ds.borderWidth ?? 2,
  }))
  chartInstances[key] = new window.Chart(el, {
    type: chartType,
    data: { labels, datasets: normalizedDatasets },
    options: baseOptions(yTitle),
  })
}

function buildBarChart(canvasRef, key, labels, datasets, yTitle, extraScales = {}) {
  const el = canvasRef.value
  if (!el) return
  destroyChart(key)
  chartInstances[key] = new window.Chart(el, {
    type: 'bar',
    data: { labels, datasets },
    options: baseOptions(yTitle, extraScales),
  })
}

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

function formatSharpeKey(key) {
  const text = String(key ?? '')
  if (!text) return text
  if (text === 'all') return 'all'
  const pastMatch = text.match(/^past_(\d+)(?:_.*)?$/)
  if (pastMatch) {
    return `近${Number(pastMatch[1])}年`
  }
  const yearMatch = text.match(/^year_\d+_(\d{4})$/)
  if (yearMatch) {
    return yearMatch[1]
  }
  return text
}

function sharpeEntriesToSeries(obj) {
  const entries = []
  if (!obj || typeof obj !== 'object') return entries
  Object.entries(obj).forEach(([key, value]) => {
    if (!value || typeof value !== 'object') return
    if (value.sharpe_ratio === undefined || value.sharpe_ratio === null) return
    entries.push({ key: formatSharpeKey(key), sharpe: value.sharpe_ratio })
  })
  entries.sort((a, b) => {
    if (a.key === 'all' && b.key !== 'all') return -1
    if (b.key === 'all' && a.key !== 'all') return 1
    return a.key.localeCompare(b.key)
  })
  return entries
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

function repairDaysValues(data) {
  return [
    ['index', data.index_maximum_number_of_backtest_repair_days],
    ['start', data.start_maximum_number_of_backtest_repair_days],
    ['excess', data.excess_maximum_number_of_backtest_repair_days],
  ].filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(Number(value)))
}

async function renderCharts(data) {
  const Chart = await loadChartJs()
  if (!Chart || !result.value) return

  const idxAnnual = normalizeYearSeries(data.index_returns_rate, 'annual_return')
  const stAnnual = normalizeYearSeries(data.start_returns_rate, 'annual_return')
  const labelsAnnual = Array.from(new Set([...idxAnnual.labels, ...stAnnual.labels])).sort()
  const idxAnnualVals = labelsAnnual.map((year) => idxAnnual.map.get(year) ?? null)
  const stAnnualVals = labelsAnnual.map((year) => stAnnual.map.get(year) ?? null)

  buildLineChart(chartAnnualReturns, 'annualReturns', labelsAnnual, [
    {
      label: '指数年度收益(%)',
      data: idxAnnualVals.map((value) => (value === null ? null : value * 100)),
      borderColor: '#0d6efd',
      backgroundColor: 'rgba(13,110,253,0.08)',
      tension: 0.1,
      fill: true,
    },
    {
      label: '模型年度收益(%)',
      data: stAnnualVals.map((value) => (value === null ? null : value * 100)),
      borderColor: '#198754',
      backgroundColor: 'rgba(25,135,84,0.08)',
      tension: 0.1,
      fill: true,
    },
  ], 'Return (%)')

  const exMap = new Map()
  if (Array.isArray(data.excess_returns)) {
    data.excess_returns.forEach((item) => {
      const year = String(item.year)
      if (year === 'all') return
      exMap.set(year, item.annualized_return_diff)
    })
  }
  const exLabels = Array.from(exMap.keys()).sort()
  const exVals = exLabels.map((year) => (exMap.get(year) ?? 0) * 100)
  buildBarChart(chartExcessAnnual, 'excessAnnual', exLabels, [{
    label: '年超额收益 (%)',
    data: exVals,
    backgroundColor: exVals.map((value) => (value >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)')),
    borderColor: exVals.map((value) => (value >= 0 ? '#198754' : '#dc3545')),
    borderWidth: 1,
  }], 'Excess Return (%)')

  const idxDd = normalizeYearSeries(data.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const stDd = normalizeYearSeries(data.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const ddLabels = Array.from(new Set([...idxDd.labels, ...stDd.labels])).sort()
  const idxDdVals = ddLabels.map((year) => idxDd.map.get(year) ?? null)
  const stDdVals = ddLabels.map((year) => stDd.map.get(year) ?? null)
  buildLineChart(chartAnnualDrawdown, 'annualDrawdown', ddLabels, [
    {
      label: '指数最大回撤 (%)',
      data: idxDdVals.map((value) => (value === null ? null : value * 100)),
      borderColor: '#dc3545',
      backgroundColor: 'rgba(220,53,69,0.08)',
      tension: 0.1,
      fill: true,
    },
    {
      label: '模型最大回撤 (%)',
      data: stDdVals.map((value) => (value === null ? null : value * 100)),
      borderColor: '#fd7e14',
      backgroundColor: 'rgba(253,126,20,0.08)',
      tension: 0.1,
      fill: true,
    },
  ], 'Drawdown (%)')

  const kamaIdx = normalizeYearSeries(data.index_kama_ratio, 'kama_ratio')
  const kamaSt = normalizeYearSeries(data.start_kama_ratio, 'kama_ratio')
  const kamaLabels = Array.from(new Set([...kamaIdx.labels, ...kamaSt.labels])).sort()
  buildLineChart(chartKama, 'kama', kamaLabels, [
    {
      label: '指数Kama',
      data: kamaLabels.map((year) => kamaIdx.map.get(year) ?? null),
      borderColor: '#0dcaf0',
      backgroundColor: 'rgba(13,202,240,0.08)',
      tension: 0.1,
      fill: true,
    },
    {
      label: '模型Kama',
      data: kamaLabels.map((year) => kamaSt.map.get(year) ?? null),
      borderColor: '#6610f2',
      backgroundColor: 'rgba(102,16,242,0.08)',
      tension: 0.1,
      fill: true,
    },
  ], 'Kama Ratio')

  const sotIdx = normalizeYearSeries(data.index_sortino_ratio, 'sortino_ratio')
  const sotSt = normalizeYearSeries(data.start_sortino_ratio, 'sortino_ratio')
  const sotLabels = Array.from(new Set([...sotIdx.labels, ...sotSt.labels])).sort()
  buildLineChart(chartSotino, 'sotino', sotLabels, [
    {
      label: '指数Sotino',
      data: sotLabels.map((year) => sotIdx.map.get(year) ?? null),
      borderColor: '#20c997',
      backgroundColor: 'rgba(32,201,151,0.08)',
      tension: 0.1,
      fill: true,
    },
    {
      label: '模型Sotino',
      data: sotLabels.map((year) => sotSt.map.get(year) ?? null),
      borderColor: '#d63384',
      backgroundColor: 'rgba(214,51,132,0.08)',
      tension: 0.1,
      fill: true,
    },
  ], 'Sotino Ratio')

  const volEl = chartMonthlyVol.value
  if (volEl) {
    destroyChart('monthlyVol')
    chartInstances.monthlyVol = new Chart(volEl, {
      type: 'bar',
      data: {
        labels: ['指数', '模型'],
        datasets: [{
          label: '月收益率波动率',
          data: [
            data.index_monthly_return_volatility !== undefined ? data.index_monthly_return_volatility : null,
            data.start_monthly_return_volatility !== undefined ? data.start_monthly_return_volatility : null,
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

  renderMonthlyExcessReturnsChart(Chart, data)
  renderSharpeCompare(Chart, data)
  renderExcessMetricsChart(Chart, data)
  renderRepairDaysChart(Chart, data)
  renderProfitMonthly(Chart, data)
}

function renderMonthlyExcessReturnsChart(Chart, data) {
  const el = chartMonthlyExcessReturns.value
  if (!el) return
  destroyChart('monthlyExcessReturns')

  const list = Array.isArray(data.monthly_excess_returns) ? data.monthly_excess_returns : []
  const sorted = list
    .filter((item) => item && item.year_month)
    .slice()
    .sort((a, b) => String(a.year_month).localeCompare(String(b.year_month)))

  const labels = sorted.map((item) => String(item.year_month))
  const values = sorted.map((item) => (item.monthly_excess_return_diff ?? null))
  const valuesPct = values.map((value) => (value === null ? null : Number(value) * 100))

  chartInstances.monthlyExcessReturns = new Chart(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '月超额收益 (%)',
        data: valuesPct,
        backgroundColor: values.map((value) => ((value ?? 0) >= 0 ? 'rgba(25,135,84,0.55)' : 'rgba(220,53,69,0.55)')),
        borderColor: values.map((value) => ((value ?? 0) >= 0 ? '#198754' : '#dc3545')),
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

function renderSharpeCompare(Chart, data) {
  const el = chartSharpeCompare.value
  if (!el) return
  destroyChart('sharpeCompare')

  const idxSeries = sharpeEntriesToSeries(data.index_sharpe_ratios)
  const stSeries = sharpeEntriesToSeries(data.start_sharpe_ratios)
  const labels = Array.from(new Set([...idxSeries.map((item) => item.key), ...stSeries.map((item) => item.key)])).sort((a, b) => {
    if (a === 'all' && b !== 'all') return -1
    if (b === 'all' && a !== 'all') return 1
    return String(a).localeCompare(String(b))
  })
  const idxMap = new Map(idxSeries.map((item) => [item.key, item.sharpe]))
  const stMap = new Map(stSeries.map((item) => [item.key, item.sharpe]))

  chartInstances.sharpeCompare = new Chart(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: '指数夏普',
          data: labels.map((key) => idxMap.get(key) ?? null),
          backgroundColor: 'rgba(13,110,253,0.45)',
          borderColor: '#0d6efd',
          borderWidth: 1,
        },
        {
          label: '模型夏普',
          data: labels.map((key) => stMap.get(key) ?? null),
          backgroundColor: 'rgba(25,135,84,0.45)',
          borderColor: '#198754',
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { title: { display: true, text: 'Sharpe Ratio' } },
        x: { ticks: { autoSkip: false, maxRotation: 60, minRotation: 20 } },
      },
    },
  })
}

function renderExcessMetricsChart(Chart, data) {
  const el = chartExcessMetrics.value
  if (!el) return
  destroyChart('excessMetrics')
  chartInstances.excessMetrics = new Chart(el, {
    type: 'bar',
    data: {
      labels: ['excess_sharpe', 'excess_sortino'],
      datasets: [{
        label: 'Value',
        data: [data.excess_sharpe ?? null, data.excess_sortino ?? null],
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

function renderRepairDaysChart(Chart, data) {
  const el = chartRepairDays.value
  if (!el) return
  destroyChart('repairDays')

  const rows = repairDaysValues(data)
  if (!rows.length) return

  chartInstances.repairDays = new Chart(el, {
    type: 'bar',
    data: {
      labels: rows.map(([key]) => key),
      datasets: [{
        label: 'Repair Days',
        data: rows.map(([, value]) => Number(value)),
        backgroundColor: ['rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)', 'rgba(253,126,20,0.45)'].slice(0, rows.length),
        borderColor: ['#0d6efd', '#198754', '#fd7e14'].slice(0, rows.length),
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

function renderProfitMonthly(Chart, data) {
  const el = chartProfitMonthly.value
  if (!el) return
  destroyChart('profitMonthly')

  const idxMap = profitMonthlySeries(data.index_profit_monthly)
  const stMap = profitMonthlySeries(data.start_profit_monthly)
  const labels = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort()

  chartInstances.profitMonthly = new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '指数盈利月占比 (%)',
          data: labels.map((year) => {
            const value = idxMap.get(year)
            return value === null || value === undefined ? null : value * 100
          }),
          borderColor: '#0d6efd',
          backgroundColor: 'rgba(13,110,253,0.08)',
          tension: 0.1,
          fill: true,
        },
        {
          label: '模型盈利月占比 (%)',
          data: labels.map((year) => {
            const value = stMap.get(year)
            return value === null || value === undefined ? null : value * 100
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

onMounted(loadResult)

onUnmounted(() => {
  destroyAllCharts()
  document.title = 'Jaspil 任务平台'
})
</script>

<style scoped>
.backtest-result-page__summary-grid {
  margin-bottom: 4px;
}

.backtest-result-page__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

.backtest-result-page__summary-col,
.backtest-result-page__detail-col {
  margin-bottom: 12px;
}

.backtest-result-page__chart-col {
  margin-bottom: 12px;
}

.backtest-result-page__chart-box {
  height: 320px;
}

.backtest-result-page__chart-box--tall {
  height: 340px;
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
