<template>
  <div class="app-page xpl-v1-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">XPL</div>
        <h2 class="page-title">V1：Google Sheet 分析</h2>
      </div>
      <div class="page-toolbar__actions">
      <el-button @click="$router.push('/xpl')">返回</el-button>
      </div>
    </div>

    <!-- 输入区 -->
    <el-card shadow="never" class="section-card">
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :lg="14">
          <el-form-item label="Google Sheet URL">
            <el-input v-model="gsUrl" placeholder="https://docs.google.com/spreadsheets/d/..." @input="onUrlInput" clearable />
            <div class="helper-text xpl-v1-page__meta">{{ gsMeta }}</div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :lg="6">
          <el-form-item label="工作表">
            <el-select v-model="sheetName" :disabled="!worksheets.length" class="full-width" placeholder="请先获取工作表">
              <el-option v-for="w in worksheets" :key="w" :value="w" :label="w" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :lg="2">
          <el-button @click="fetchSheets" :loading="fetchingSheets">获取</el-button>
        </el-col>
        <el-col :xs="12" :lg="2">
          <el-button type="primary" :disabled="!sheetName" :loading="analyzing" @click="analyzeV1">分析</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 汇总卡片 -->
    <el-row :gutter="12" class="xpl-v1-summary-grid" id="summary-cards">
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--primary">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">跑赢年份</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtPct(result.outperform_year) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">outperform_year</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--success">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">月超额波动率</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtNum(result.monthly_excess_volatility, 4) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">monthly_excess_volatility</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--warning">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">超额回撤胜率</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtPct(result.excess_drawdown_winning_rate) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">excess_drawdown_winning_rate</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--danger">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">年超额收益(整体)</div>
            <div class="xpl-v1-summary-card__value">{{ excessReturnsAll }}</div>
            <div class="xpl-v1-summary-card__key">excess_returns[all]</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--neutral">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">指数盈利年%</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtPct(result.index_profit_annual) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">index_profit_annual</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--neutral">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">模型盈利年%</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtPct(result.start_profit_annual) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">start_profit_annual</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--neutral">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">指数月波动率</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtNum(result.index_monthly_return_volatility, 6) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">index_monthly_return_volatility</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="xpl-v1-summary-grid__col">
        <el-card shadow="never" class="xpl-v1-summary-card xpl-v1-summary-card--neutral">
          <div class="xpl-v1-summary-card__body">
            <div class="xpl-v1-summary-card__label">模型月波动率</div>
            <div class="xpl-v1-summary-card__value">{{ result ? fmtNum(result.start_monthly_return_volatility, 6) : '-' }}</div>
            <div class="xpl-v1-summary-card__key">start_monthly_return_volatility</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 详情折叠 -->
    <el-card v-if="result" shadow="never" class="section-card" id="details-card">
      <div class="xpl-v1-detail-toolbar">
        <el-button size="small" @click="detailOpen = !detailOpen">
          {{ detailOpen ? '收起' : '展开' }} V1 数据明细
        </el-button>
        <el-button size="small" type="primary" @click="exportResult">导出并下载</el-button>
      </div>
      <div v-if="detailOpen">
        <el-tabs v-model="activeTab" tab-position="left">
          <el-tab-pane label="年度收益/回撤" name="annual">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="xpl-v1-block-col">
                <div class="xpl-v1-block-title">年度收益率对比</div>
                <el-table :data="annualCompareRows" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="指数收益"><template #default="{row}"><span :class="colorClass(row.index_return)">{{ fmtPct(row.index_return) }}</span></template></el-table-column>
                  <el-table-column label="模型收益"><template #default="{row}"><span :class="colorClass(row.model_return)">{{ fmtPct(row.model_return) }}</span></template></el-table-column>
                  <el-table-column label="差值"><template #default="{row}"><span :class="colorClass(row.diff)">{{ fmtPct(row.diff) }}</span></template></el-table-column>
                </el-table>
              </el-col>
              <el-col :xs="24" :lg="12" class="xpl-v1-block-col">
                <div class="xpl-v1-block-title">年度最大回撤对比</div>
                <el-table :data="drawdownCompareRows" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="指数回撤"><template #default="{row}"><span class="text-danger">-{{ fmtPct(row.index_dd) }}</span></template></el-table-column>
                  <el-table-column label="模型回撤"><template #default="{row}"><span class="text-danger">-{{ fmtPct(row.model_dd) }}</span></template></el-table-column>
                  <el-table-column prop="dates" label="日期(指数/模型)" min-width="140" show-overflow-tooltip />
                </el-table>
              </el-col>
              <el-col :xs="24">
                <div class="xpl-v1-block-title">月超额收益百分比</div>
                <el-table :data="result.monthly_excess_return_percentage || []" stripe size="small" border>
                  <el-table-column prop="year" label="Year" width="80" />
                  <el-table-column label="月超额收益占比"><template #default="{row}">{{ fmtPct(row.excess_return) }}</template></el-table-column>
                </el-table>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="超额收益" name="excess">
            <el-table :data="result.excess_returns || []" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="Year" width="80" />
              <el-table-column label="模型年化"><template #default="{row}"><span :class="colorClass(row.start_annualized_return)">{{ fmtPct(row.start_annualized_return) }}</span></template></el-table-column>
              <el-table-column label="指数年化"><template #default="{row}"><span :class="colorClass(row.index_annualized_return)">{{ fmtPct(row.index_annualized_return) }}</span></template></el-table-column>
              <el-table-column label="超额"><template #default="{row}"><span :class="colorClass(row.annualized_return_diff)">{{ fmtPct(row.annualized_return_diff) }}</span></template></el-table-column>
              <el-table-column prop="start_end_date" label="区间" min-width="140" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="月超额收益" name="monthly_excess">
            <el-table :data="result.monthly_excess_returns || []" stripe size="small" border max-height="500">
              <el-table-column prop="year_month" label="年月" width="100" />
              <el-table-column label="指数月收益"><template #default="{row}"><span :class="colorClass(row.index_monthly_return)">{{ fmtPct(row.index_monthly_return) }}</span></template></el-table-column>
              <el-table-column label="模型月收益"><template #default="{row}"><span :class="colorClass(row.start_monthly_return)">{{ fmtPct(row.start_monthly_return) }}</span></template></el-table-column>
              <el-table-column label="超额差值"><template #default="{row}"><span :class="colorClass(row.monthly_excess_return_diff)">{{ fmtPct(row.monthly_excess_return_diff) }}</span></template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="卡玛比率" name="kama">
            <el-table :data="kamaRows" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数Kama"><template #default="{row}">{{ fmtNum(row.index_kama, 6) }}</template></el-table-column>
              <el-table-column label="模型Kama"><template #default="{row}">{{ fmtNum(row.model_kama, 6) }}</template></el-table-column>
              <el-table-column label="指数年化"><template #default="{row}">{{ fmtPct(row.index_annual) }}</template></el-table-column>
              <el-table-column label="模型年化"><template #default="{row}">{{ fmtPct(row.model_annual) }}</template></el-table-column>
              <el-table-column label="指数回撤"><template #default="{row}">{{ fmtPct(row.index_dd) }}</template></el-table-column>
              <el-table-column label="模型回撤"><template #default="{row}">{{ fmtPct(row.model_dd) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="所提诺比例" name="sotino">
            <el-table :data="sotinoRows" stripe size="small" border max-height="500">
              <el-table-column prop="year" label="年份" width="80" />
              <el-table-column label="指数"><template #default="{row}">{{ fmtNum(row.index_sotino, 6) }}</template></el-table-column>
              <el-table-column label="模型"><template #default="{row}">{{ fmtNum(row.model_sotino, 6) }}</template></el-table-column>
              <el-table-column label="指数平均月收益"><template #default="{row}">{{ fmtNum(row.index_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="模型平均月收益"><template #default="{row}">{{ fmtNum(row.model_avg_monthly, 6) }}</template></el-table-column>
              <el-table-column label="指数下行标准差"><template #default="{row}">{{ fmtNum(row.index_downside_std, 6) }}</template></el-table-column>
              <el-table-column label="模型下行标准差"><template #default="{row}">{{ fmtNum(row.model_downside_std, 6) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="夏普比率" name="sharpe">
            <el-table :data="sharpeRows" stripe size="small" border max-height="500">
              <el-table-column prop="period" label="区间" width="100" />
              <el-table-column label="指数夏普"><template #default="{row}">{{ fmtNum(row.index_sharpe, 6) }}</template></el-table-column>
              <el-table-column label="模型夏普"><template #default="{row}">{{ fmtNum(row.model_sharpe, 6) }}</template></el-table-column>
              <el-table-column label="指数平均月收益"><template #default="{row}">{{ fmtPct(row.index_avg_monthly) }}</template></el-table-column>
              <el-table-column label="模型平均月收益"><template #default="{row}">{{ fmtPct(row.model_avg_monthly) }}</template></el-table-column>
              <el-table-column label="指数月波动"><template #default="{row}">{{ fmtPct(row.index_monthly_std) }}</template></el-table-column>
              <el-table-column label="模型月波动"><template #default="{row}">{{ fmtPct(row.model_monthly_std) }}</template></el-table-column>
              <el-table-column label="指数年波动"><template #default="{row}">{{ fmtPct(row.index_annual_std) }}</template></el-table-column>
              <el-table-column label="模型年波动"><template #default="{row}">{{ fmtPct(row.model_annual_std) }}</template></el-table-column>
              <el-table-column prop="start_date" label="开始" width="100" />
              <el-table-column prop="end_date" label="结束" width="100" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="超额指标" name="excess_metrics">
            <el-table :data="excessMetricsRows" stripe size="small" border>
              <el-table-column prop="key" label="Key" width="220"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="value" label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="回测修复天数" name="repair_days">
            <el-table :data="repairDaysRows" stripe size="small" border>
              <el-table-column prop="metric" label="Metric" width="120"><template #default="{row}"><code>{{ row.metric }}</code></template></el-table-column>
              <el-table-column prop="value" label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="盈利统计" name="profit">
            <el-row :gutter="12">
              <el-col :xs="24" :lg="12" class="xpl-v1-block-col">
                <div class="xpl-v1-block-title">盈利年百分比</div>
                <el-table :data="profitAnnualRow" stripe size="small" border>
                  <el-table-column label="指数"><template #default="{row}">{{ fmtPct(row.index) }}</template></el-table-column>
                  <el-table-column label="模型"><template #default="{row}">{{ fmtPct(row.model) }}</template></el-table-column>
                </el-table>
              </el-col>
              <el-col :xs="24" :lg="12">
                <el-row :gutter="12">
                  <el-col :xs="24" class="xpl-v1-block-col">
                    <div class="xpl-v1-block-title">指数盈利月占比</div>
                    <el-table :data="result.index_profit_monthly || []" stripe size="small" border max-height="200">
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="占比"><template #default="{row}">{{ fmtPct(row.profit_monthly_percentage) }}</template></el-table-column>
                    </el-table>
                  </el-col>
                  <el-col :xs="24">
                    <div class="xpl-v1-block-title">模型盈利月占比</div>
                    <el-table :data="result.start_profit_monthly || []" stripe size="small" border max-height="200">
                      <el-table-column prop="year" label="Year" width="80" />
                      <el-table-column label="占比"><template #default="{row}">{{ fmtPct(row.profit_monthly_percentage) }}</template></el-table-column>
                    </el-table>
                  </el-col>
                </el-row>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane label="关键标量" name="scalars">
            <el-table :data="scalarsRows" stripe size="small" border max-height="500">
              <el-table-column prop="key" label="Key" width="280"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="name" label="Name" width="180" />
              <el-table-column prop="value" label="Value" />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="Sheet 结果" name="sheet_result">
            <el-table :data="sheetResultRows" stripe size="small" border max-height="500">
              <el-table-column prop="key" label="Key" width="220"><template #default="{row}"><code>{{ row.key }}</code></template></el-table-column>
              <el-table-column prop="value" label="Value" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="全量 JSON" name="raw">
            <div class="xpl-v1-raw-toolbar">
              <el-button size="small" @click="copyRawJson">复制</el-button>
            </div>
            <pre class="mono-pre xpl-v1-raw-json">{{ JSON.stringify(result, null, 2) }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>

    <!-- 图表区 -->
    <el-card v-if="result" shadow="never" class="section-card">
      <div class="xpl-v1-chart-title">V1 图表</div>
      <el-row :gutter="12">
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">年度收益率（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartAnnualReturns"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">年超额收益（模型 - 指数）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartExcessAnnual"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">年度最大回撤（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartAnnualDrawdown"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">卡玛比率（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartKama"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">所提诺比例（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartSotino"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">月收益率波动率（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartMonthlyVol"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">月超额收益（模型 - 指数）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--340"><canvas ref="chartMonthlyExcess"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">夏普比率对比（all / year_* / past_*）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--340"><canvas ref="chartSharpeCompare"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">超额指标（夏普 / 索提诺）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartExcessMetrics"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">最大回测修复天数（index / start / excess）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartRepairDays"></canvas></div></el-card>
        </el-col>
        <el-col :xs="24" class="xpl-v1-chart-col">
          <el-card shadow="never"><div class="xpl-v1-block-title">盈利月百分比（指数 vs 模型）</div><div class="xpl-v1-chart-box xpl-v1-chart-box--320"><canvas ref="chartProfitMonthly"></canvas></div></el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-if="!analyzing && !result" description="输入 Google Sheet URL 并点击分析" />
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { analyzeXplV1, exportXplResult } from '@/api/xpl'

// ── state ────────────────────────────────────────────────────
const gsUrl = ref('')
const gsMeta = ref('')
const sheetName = ref('')
const worksheets = ref([])
const fetchingSheets = ref(false)
const analyzing = ref(false)
const result = ref(null)
const detailOpen = ref(false)
const activeTab = ref('annual')

// chart canvas refs
const chartAnnualReturns = ref(null)
const chartExcessAnnual = ref(null)
const chartAnnualDrawdown = ref(null)
const chartKama = ref(null)
const chartSotino = ref(null)
const chartMonthlyVol = ref(null)
const chartMonthlyExcess = ref(null)
const chartSharpeCompare = ref(null)
const chartExcessMetrics = ref(null)
const chartRepairDays = ref(null)
const chartProfitMonthly = ref(null)

const chartInstances = {}

// ── URL helpers ──────────────────────────────────────────────
function extractSpreadsheetId(url) {
  const m = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/)
  return m ? m[1] : ''
}

let urlDebounceTimer = null
function onUrlInput() {
  worksheets.value = []; sheetName.value = ''; gsMeta.value = ''
  clearTimeout(urlDebounceTimer)
  urlDebounceTimer = setTimeout(() => {
    if (gsUrl.value.trim()) fetchSheets()
  }, 800)
}

// ── API calls ────────────────────────────────────────────────
async function fetchSheets() {
  const url = gsUrl.value.trim()
  if (!url) { ElMessage.warning('请输入 Google Sheet URL'); return }
  const spreadsheetId = extractSpreadsheetId(url)
  if (!spreadsheetId) { ElMessage.warning('无法从 URL 中提取 spreadsheet_id'); return }
  fetchingSheets.value = true
  try {
    const res = await api.post('/google-sheet/worksheets', { spreadsheet_id: spreadsheetId })
    worksheets.value = res.worksheets || res.sheets || []
    gsMeta.value = res.title || spreadsheetId
    if (worksheets.value.length) sheetName.value = worksheets.value[0]
    ElMessage.success('获取成功')
  } catch { ElMessage.error('获取工作表失败') }
  finally { fetchingSheets.value = false }
}

async function analyzeV1() {
  const url = gsUrl.value.trim()
  if (!url || !sheetName.value) { ElMessage.warning('请先获取工作表'); return }
  const spreadsheetId = extractSpreadsheetId(url)
  analyzing.value = true
  result.value = null
  try {
    const payload = await analyzeXplV1({
      google_sheet_url: url,
      spreadsheet_id: spreadsheetId,
      google_sheet_name: sheetName.value
    })
    result.value = payload?.result || payload
    ElMessage.success('分析完成')
    await nextTick()
    renderCharts(result.value)
  } catch (error) { ElMessage.error(error?.message || '分析失败') }
  finally { analyzing.value = false }
}

// ── formatters ───────────────────────────────────────────────
function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return (Number(v) * 100).toFixed(digits) + '%'
}
function fmtNum(v, digits = 4) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return Number(v).toFixed(digits)
}
function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  return String(Math.round(Number(v)))
}
function colorClass(v) { return (Number(v) || 0) >= 0 ? 'text-success' : 'text-danger' }

// ── computed rows (same logic as Result.vue) ─────────────────
const excessReturnsAll = computed(() => {
  if (!result.value) return '-'
  const all = Array.isArray(result.value.excess_returns)
    ? result.value.excess_returns.find(x => String(x.year) === 'all') : null
  return all ? fmtPct(all.annualized_return_diff) : '-'
})

const annualCompareRows = computed(() => {
  if (!result.value) return []
  const idxMap = new Map(); const stMap = new Map()
  ;(result.value.index_returns_rate || []).forEach(x => { if (String(x.year) !== 'all') idxMap.set(String(x.year), x.annual_return) })
  ;(result.value.start_returns_rate || []).forEach(x => { if (String(x.year) !== 'all') stMap.set(String(x.year), x.annual_return) })
  const years = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort()
  return years.map(y => { const a1 = idxMap.get(y); const a2 = stMap.get(y); return { year: y, index_return: a1, model_return: a2, diff: (a2 != null && a1 != null) ? a2 - a1 : null } })
})

const drawdownCompareRows = computed(() => {
  if (!result.value) return []
  const idxMap = new Map(); const stMap = new Map()
  ;(result.value.index_maximum_drawdown?.year_maximum_drawdown || []).forEach(x => { if (String(x.year) !== 'all') idxMap.set(String(x.year), x) })
  ;(result.value.start_maximum_drawdown?.year_maximum_drawdown || []).forEach(x => { if (String(x.year) !== 'all') stMap.set(String(x.year), x) })
  const years = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort()
  return years.map(y => { const d1 = idxMap.get(y); const d2 = stMap.get(y); return { year: y, index_dd: d1?.drawdown, model_dd: d2?.drawdown, dates: `${d1?.date || '-'} / ${d2?.date || '-'}` } })
})

const kamaRows = computed(() => {
  if (!result.value) return []
  const idxMap = new Map(); const stMap = new Map()
  ;(result.value.index_kama_ratio || []).forEach(x => { if (String(x.year) !== 'all') idxMap.set(String(x.year), x) })
  ;(result.value.start_kama_ratio || []).forEach(x => { if (String(x.year) !== 'all') stMap.set(String(x.year), x) })
  const years = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort()
  return years.map(y => { const i = idxMap.get(y); const s = stMap.get(y); return { year: y, index_kama: i?.kama_ratio, model_kama: s?.kama_ratio, index_annual: i?.annualized_return, model_annual: s?.annualized_return, index_dd: i?.drawdown, model_dd: s?.drawdown } })
})

const sotinoRows = computed(() => {
  if (!result.value) return []
  const idxMap = new Map(); const stMap = new Map()
  ;(result.value.index_sotino_ratio || []).forEach(x => { if (String(x.year) !== 'all') idxMap.set(String(x.year), x) })
  ;(result.value.start_sotino_ratio || []).forEach(x => { if (String(x.year) !== 'all') stMap.set(String(x.year), x) })
  const years = Array.from(new Set([...idxMap.keys(), ...stMap.keys()])).sort()
  return years.map(y => { const i = idxMap.get(y); const s = stMap.get(y); return { year: y, index_sotino: i?.sotino_ratio, model_sotino: s?.sotino_ratio, index_avg_monthly: i?.average_monthly_annualized_return, model_avg_monthly: s?.average_monthly_annualized_return, index_downside_std: i?.downside_standard_deviation, model_downside_std: s?.downside_standard_deviation } })
})

const sharpeRows = computed(() => {
  if (!result.value) return []
  const idx = result.value.index_sharpe_ratios || {}; const st = result.value.start_sharpe_ratios || {}
  const keys = Array.from(new Set([...Object.keys(idx), ...Object.keys(st)])).sort()
  return keys.map(k => { const i = idx[k]; const s = st[k]; const base = i || s; return { period: k, index_sharpe: i?.sharpe_ratio, model_sharpe: s?.sharpe_ratio, index_avg_monthly: i?.avg_monthly_return, model_avg_monthly: s?.avg_monthly_return, index_monthly_std: i?.monthly_std_dev, model_monthly_std: s?.monthly_std_dev, index_annual_std: i?.annual_std_dev, model_annual_std: s?.annual_std_dev, start_date: base?.start_date, end_date: base?.end_date } })
})

const excessMetricsRows = computed(() => {
  if (!result.value) return []
  return [{ key: 'excess_sharp', value: fmtNum(result.value.excess_sharp, 6) }, { key: 'excess_of_promissory_note', value: fmtNum(result.value.excess_of_promissory_note, 6) }]
})

const repairDaysRows = computed(() => {
  if (!result.value) return []
  return [['index', result.value.index_maximum_number_of_backtest_repair_days], ['start', result.value.start_maximum_number_of_backtest_repair_days], ['excess', result.value.excess_maximum_number_of_backtest_repair_days]].filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => ({ metric: k, value: fmtInt(v) }))
})

const profitAnnualRow = computed(() => {
  if (!result.value) return []
  return [{ index: result.value.index_profit_annual, model: result.value.start_profit_annual }]
})

const SCALAR_NAME_MAP = { outperform_year: '跑赢年份', monthly_excess_volatility: '月超额波动率', excess_drawdown_winning_rate: '超额回撤胜率', excess_sharp: '超额夏普', excess_of_promissory_note: '超额所提诺', index_profit_annual: '指数盈利年百分比', start_profit_annual: '策略盈利年百分比', index_monthly_return_volatility: '指数月收益率波动率', start_monthly_return_volatility: '策略月收益率波动率', index_maximum_number_of_backtest_repair_days: '指数最大回测天数', start_maximum_number_of_backtest_repair_days: '策略最大回测天数', excess_maximum_number_of_backtest_repair_days: '超额最大回测天数' }

const scalarsRows = computed(() => {
  if (!result.value) return []
  return Object.keys(SCALAR_NAME_MAP).filter(k => result.value[k] !== undefined).map(k => {
    let v = result.value[k]
    if (k.includes('profit_annual') || k.includes('outperform_year') || k.includes('winning_rate')) v = fmtPct(v)
    else if (k.includes('maximum_number_of_backtest_repair_days')) v = fmtInt(v)
    else if (typeof v === 'number') v = fmtNum(v, 6)
    return { key: k, name: SCALAR_NAME_MAP[k] || '-', value: v }
  })
})

const sheetResultRows = computed(() => {
  if (!result.value?.sheet_result || typeof result.value.sheet_result !== 'object') return []
  return Object.keys(result.value.sheet_result).sort().map(k => ({ key: k, value: typeof result.value.sheet_result[k] === 'object' ? JSON.stringify(result.value.sheet_result[k]) : String(result.value.sheet_result[k] ?? '') }))
})

// ── export / copy ────────────────────────────────────────────
async function exportResult() {
  if (!result.value) return
  const exportBaseName = `v1_${sheetName.value || 'result'}`
  try {
    const blob = await exportXplResult({ filename: `${exportBaseName}.csv`, filename_title: exportBaseName, analyze_result: result.value })
    const filename = prompt('请输入文件名:', `${exportBaseName}.csv`) || `${exportBaseName}.csv`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch {
    const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `${exportBaseName}.json`; a.click()
    URL.revokeObjectURL(url)
  }
}

async function copyRawJson() {
  try { await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2)); ElMessage.success('复制成功') }
  catch { ElMessage.error('复制失败') }
}

// ── charts (Chart.js loaded from CDN) ───────────────────────
function loadChartJs() {
  return new Promise((resolve, reject) => {
    if (window.Chart) { resolve(window.Chart); return }
    const s = document.createElement('script')
    s.src = 'https://cdn.jsdelivr.net/npm/chart.js'
    s.onload = () => resolve(window.Chart)
    s.onerror = reject
    document.head.appendChild(s)
  })
}

function destroyChart(key) {
  if (chartInstances[key]) { try { chartInstances[key].destroy() } catch {} chartInstances[key] = null }
}

function buildChart(Chart, canvasRef, key, type, labels, datasets, options = {}) {
  const el = canvasRef.value
  if (!el) return
  destroyChart(key)
  chartInstances[key] = new Chart(el, {
    type,
    data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, ...options }
  })
}

function normYearSeries(list, valueKey) {
  const m = new Map()
  if (Array.isArray(list)) list.forEach(x => { if (x && String(x.year) !== 'all') m.set(String(x.year), x[valueKey]) })
  const labels = Array.from(m.keys()).sort()
  return { labels, map: m }
}

async function renderCharts(r) {
  let Chart
  try { Chart = await loadChartJs() } catch { return }

  // 1. annual returns
  const idxA = normYearSeries(r.index_returns_rate, 'annual_return')
  const stA = normYearSeries(r.start_returns_rate, 'annual_return')
  const labA = Array.from(new Set([...idxA.labels, ...stA.labels])).sort()
  buildChart(Chart, chartAnnualReturns, 'annualReturns', 'line', labA, [
    { label: '指数年度收益(%)', data: labA.map(y => (idxA.map.get(y) ?? null) === null ? null : idxA.map.get(y) * 100), borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.08)', tension: 0.1, fill: true },
    { label: '模型年度收益(%)', data: labA.map(y => (stA.map.get(y) ?? null) === null ? null : stA.map.get(y) * 100), borderColor: '#198754', backgroundColor: 'rgba(25,135,84,0.08)', tension: 0.1, fill: true }
  ], { scales: { y: { title: { display: true, text: 'Return (%)' } } } })

  // 2. excess annual
  const exMap = new Map()
  if (Array.isArray(r.excess_returns)) r.excess_returns.forEach(x => { if (String(x.year) !== 'all') exMap.set(String(x.year), x.annualized_return_diff) })
  const exLabels = Array.from(exMap.keys()).sort()
  const exVals = exLabels.map(y => (exMap.get(y) ?? 0) * 100)
  buildChart(Chart, chartExcessAnnual, 'excessAnnual', 'bar', exLabels, [
    { label: '年超额收益(%)', data: exVals, backgroundColor: exVals.map(v => v >= 0 ? 'rgba(25,135,84,0.5)' : 'rgba(220,53,69,0.5)'), borderColor: exVals.map(v => v >= 0 ? '#198754' : '#dc3545'), borderWidth: 1 }
  ], { scales: { y: { title: { display: true, text: 'Excess Return (%)' } } } })

  // 3. annual drawdown
  const idxD = normYearSeries(r.index_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const stD = normYearSeries(r.start_maximum_drawdown?.year_maximum_drawdown, 'drawdown')
  const labD = Array.from(new Set([...idxD.labels, ...stD.labels])).sort()
  buildChart(Chart, chartAnnualDrawdown, 'annualDrawdown', 'line', labD, [
    { label: '指数最大回撤(%)', data: labD.map(y => (idxD.map.get(y) ?? null) === null ? null : idxD.map.get(y) * 100), borderColor: '#dc3545', backgroundColor: 'rgba(220,53,69,0.08)', tension: 0.1, fill: true },
    { label: '模型最大回撤(%)', data: labD.map(y => (stD.map.get(y) ?? null) === null ? null : stD.map.get(y) * 100), borderColor: '#fd7e14', backgroundColor: 'rgba(253,126,20,0.08)', tension: 0.1, fill: true }
  ], { scales: { y: { title: { display: true, text: 'Drawdown (%)' } } } })

  // 4. kama
  const idxK = normYearSeries(r.index_kama_ratio, 'kama_ratio'); const stK = normYearSeries(r.start_kama_ratio, 'kama_ratio')
  const labK = Array.from(new Set([...idxK.labels, ...stK.labels])).sort()
  buildChart(Chart, chartKama, 'kama', 'line', labK, [
    { label: '指数Kama', data: labK.map(y => idxK.map.get(y) ?? null), borderColor: '#0dcaf0', backgroundColor: 'rgba(13,202,240,0.08)', tension: 0.1, fill: true },
    { label: '模型Kama', data: labK.map(y => stK.map.get(y) ?? null), borderColor: '#6610f2', backgroundColor: 'rgba(102,16,242,0.08)', tension: 0.1, fill: true }
  ], { scales: { y: { title: { display: true, text: 'Kama Ratio' } } } })

  // 5. sotino
  const idxS = normYearSeries(r.index_sotino_ratio, 'sotino_ratio'); const stS = normYearSeries(r.start_sotino_ratio, 'sotino_ratio')
  const labS = Array.from(new Set([...idxS.labels, ...stS.labels])).sort()
  buildChart(Chart, chartSotino, 'sotino', 'line', labS, [
    { label: '指数Sotino', data: labS.map(y => idxS.map.get(y) ?? null), borderColor: '#20c997', backgroundColor: 'rgba(32,201,151,0.08)', tension: 0.1, fill: true },
    { label: '模型Sotino', data: labS.map(y => stS.map.get(y) ?? null), borderColor: '#d63384', backgroundColor: 'rgba(214,51,132,0.08)', tension: 0.1, fill: true }
  ], { scales: { y: { title: { display: true, text: 'Sotino Ratio' } } } })

  // 6. monthly vol (bar)
  buildChart(Chart, chartMonthlyVol, 'monthlyVol', 'bar', ['指数', '模型'], [
    { label: '月收益率波动率', data: [r.index_monthly_return_volatility ?? null, r.start_monthly_return_volatility ?? null], backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'], borderColor: ['#0d6efd', '#198754'], borderWidth: 1 }
  ], { scales: { y: { title: { display: true, text: 'Volatility' } } } })

  // 7. monthly excess returns
  const mer = Array.isArray(r.monthly_excess_returns) ? r.monthly_excess_returns.filter(x => x?.year_month).sort((a, b) => String(a.year_month).localeCompare(String(b.year_month))) : []
  const merLabels = mer.map(x => String(x.year_month))
  const merVals = mer.map(x => (x.monthly_excess_return_diff ?? null) === null ? null : Number(x.monthly_excess_return_diff) * 100)
  buildChart(Chart, chartMonthlyExcess, 'monthlyExcess', 'bar', merLabels, [
    { label: '月超额收益(%)', data: merVals, backgroundColor: merVals.map(v => (v ?? 0) >= 0 ? 'rgba(25,135,84,0.55)' : 'rgba(220,53,69,0.55)'), borderColor: merVals.map(v => (v ?? 0) >= 0 ? '#198754' : '#dc3545'), borderWidth: 1 }
  ], { scales: { y: { title: { display: true, text: 'Excess Return (%)' } }, x: { ticks: { autoSkip: true, maxRotation: 60 } } } })

  // 8. sharpe compare
  const idxSh = r.index_sharpe_ratios || {}; const stSh = r.start_sharpe_ratios || {}
  const shKeys = Array.from(new Set([...Object.keys(idxSh), ...Object.keys(stSh)])).sort((a, b) => { if (a === 'all') return -1; if (b === 'all') return 1; return a.localeCompare(b) })
  buildChart(Chart, chartSharpeCompare, 'sharpeCompare', 'bar', shKeys, [
    { label: '指数夏普', data: shKeys.map(k => idxSh[k]?.sharpe_ratio ?? null), backgroundColor: 'rgba(13,110,253,0.45)', borderColor: '#0d6efd', borderWidth: 1 },
    { label: '模型夏普', data: shKeys.map(k => stSh[k]?.sharpe_ratio ?? null), backgroundColor: 'rgba(25,135,84,0.45)', borderColor: '#198754', borderWidth: 1 }
  ], { scales: { y: { title: { display: true, text: 'Sharpe Ratio' } }, x: { ticks: { autoSkip: false, maxRotation: 60 } } } })

  // 9. excess metrics
  buildChart(Chart, chartExcessMetrics, 'excessMetrics', 'bar', ['excess_sharp', 'excess_of_promissory_note'], [
    { label: 'Value', data: [r.excess_sharp ?? null, r.excess_of_promissory_note ?? null], backgroundColor: ['rgba(13,110,253,0.5)', 'rgba(25,135,84,0.5)'], borderColor: ['#0d6efd', '#198754'], borderWidth: 1 }
  ], { scales: { y: { title: { display: true, text: 'Metric Value' } } } })

  // 10. repair days
  const rdRows = [['index', r.index_maximum_number_of_backtest_repair_days], ['start', r.start_maximum_number_of_backtest_repair_days], ['excess', r.excess_maximum_number_of_backtest_repair_days]].filter(([, v]) => v !== undefined && v !== null)
  if (rdRows.length) {
    buildChart(Chart, chartRepairDays, 'repairDays', 'bar', rdRows.map(([k]) => k), [
      { label: 'Repair Days', data: rdRows.map(([, v]) => Number(v)), backgroundColor: ['rgba(13,110,253,0.45)', 'rgba(25,135,84,0.45)', 'rgba(253,126,20,0.45)'].slice(0, rdRows.length), borderColor: ['#0d6efd', '#198754', '#fd7e14'].slice(0, rdRows.length), borderWidth: 1 }
    ], { scales: { y: { title: { display: true, text: 'Days' } } } })
  }

  // 11. profit monthly
  const idxPm = new Map(); const stPm = new Map()
  if (Array.isArray(r.index_profit_monthly)) r.index_profit_monthly.forEach(x => idxPm.set(String(x.year), x.profit_monthly_percentage))
  if (Array.isArray(r.start_profit_monthly)) r.start_profit_monthly.forEach(x => stPm.set(String(x.year), x.profit_monthly_percentage))
  const pmLabels = Array.from(new Set([...idxPm.keys(), ...stPm.keys()])).sort()
  buildChart(Chart, chartProfitMonthly, 'profitMonthly', 'line', pmLabels, [
    { label: '指数盈利月占比(%)', data: pmLabels.map(y => (idxPm.get(y) ?? null) === null ? null : idxPm.get(y) * 100), borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.08)', tension: 0.1, fill: true },
    { label: '模型盈利月占比(%)', data: pmLabels.map(y => (stPm.get(y) ?? null) === null ? null : stPm.get(y) * 100), borderColor: '#198754', backgroundColor: 'rgba(25,135,84,0.08)', tension: 0.1, fill: true }
  ], { scales: { y: { title: { display: true, text: 'Percentage (%)' }, beginAtZero: true, max: 100 } } })
}
</script>

<style scoped>
.xpl-v1-page__meta {
  min-height: 1.2em;
}

.xpl-v1-summary-grid {
  margin-bottom: 16px;
}

.xpl-v1-summary-grid__col,
.xpl-v1-chart-col,
.xpl-v1-block-col {
  margin-bottom: 12px;
}

.xpl-v1-summary-card {
  text-align: center;
}

.xpl-v1-summary-card--primary {
  border-color: #409eff;
}

.xpl-v1-summary-card--success {
  border-color: #67c23a;
}

.xpl-v1-summary-card--warning {
  border-color: #e6a23c;
}

.xpl-v1-summary-card--danger {
  border-color: #f56c6c;
}

.xpl-v1-summary-card--neutral {
  border-color: #909399;
}

.xpl-v1-summary-card__label {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
  margin-bottom: 4px;
}

.xpl-v1-summary-card__value {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 4px;
}

.xpl-v1-summary-card__key {
  color: #c0c4cc;
  font-size: 11px;
  font-family: 'Fira Code', monospace;
}

.xpl-v1-detail-toolbar,
.xpl-v1-raw-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.xpl-v1-raw-toolbar {
  justify-content: flex-end;
  margin-bottom: 8px;
}

.xpl-v1-block-title,
.xpl-v1-chart-title {
  margin-bottom: 8px;
  font-size: var(--app-font-sm);
  font-weight: 700;
}

.xpl-v1-chart-title {
  margin-bottom: 16px;
  font-size: var(--app-font-md);
}

.xpl-v1-chart-box--320 {
  height: 320px;
}

.xpl-v1-chart-box--340 {
  height: 340px;
}

.xpl-v1-raw-json {
  max-height: 500px;
}

.text-success { color: #67c23a; }
.text-danger { color: #f56c6c; }
</style>
