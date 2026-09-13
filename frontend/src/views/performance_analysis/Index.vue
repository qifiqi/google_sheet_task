<template>
  <div class="app-page performance-analyzer-index-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">绩效分析</div>
        <h2 class="page-title">数据分析工具</h2>
      </div>
      <div class="page-toolbar__actions page-toolbar__actions--tight">
        <el-button @click="refreshData">刷新</el-button>
        <el-button @click="openExportModal">导出结果</el-button>
      </div>
    </div>

    <!-- 数据输入区域 -->
    <el-card shadow="never" class="section-card">
      <div class="section-label">数据输入</div>
      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <div class="performance-analyzer-input-panel">
            <div class="performance-analyzer-input-panel__head">
              <span class="section-label performance-analyzer-input-panel__title">粘贴数据</span>
              <div class="page-toolbar__actions page-toolbar__actions--tight">
                <el-button size="small" @click="pasteFromClipboard">粘贴</el-button>
                <el-button size="small" @click="loadSampleData">示例</el-button>
                <el-button size="small" type="danger" plain @click="clearAllData">清空</el-button>
              </div>
            </div>
            <el-input
              v-model="dataInput"
              type="textarea"
              :rows="10"
              placeholder="请将 Excel 中的时间列和收益率列数据粘贴到此处，格式为：时间 收益率&#10;例如：&#10;2025-01-01 0.0234&#10;2025-01-02 -0.0156&#10;2025-01-03 0.0089&#10;&#10;注意：时间列和收益率列之间可以用 Tab、空格或逗号分隔"
              class="performance-analyzer-input-panel__textarea"
            />
            <div class="performance-analyzer-input-panel__count">{{ lineCount }} 行数据</div>
          </div>
        </el-col>

        <el-col :xs="24" :lg="7">
          <el-card shadow="never" class="performance-analyzer-fill-card">
            <div class="section-label">分析设置</div>
            <el-form label-width="80px" size="small">
              <el-form-item label="时间格式">
                <el-select v-model="timeFormat" class="full-width">
                  <el-option value="auto" label="自动检测" />
                  <el-option value="YYYY-MM-DD" label="YYYY-MM-DD" />
                  <el-option value="YYYY/MM/DD" label="YYYY/MM/DD" />
                  <el-option value="YYYY.MM.DD" label="YYYY.MM.DD" />
                </el-select>
              </el-form-item>
            </el-form>
            <div class="helper-text performance-analyzer-input-panel__hint">
              两列数据按“日期 + 收益率”计算；三列数据按“日期 + 指数收益率 + 模型收益率”同时计算。
            </div>
            <el-button type="primary" class="full-width" :loading="analyzing" @click="analyze">开始分析</el-button>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="7">
          <el-card shadow="never" class="performance-analyzer-fill-card performance-analyzer-usage-card">
            <div class="section-label">使用说明</div>
            <div class="performance-analyzer-usage-card__item">
              <span class="performance-analyzer-usage-card__step">1</span>
              <div>
                <div class="performance-analyzer-usage-card__title">复制数据</div>
                <div class="helper-text">从 Excel 复制数据（包含表头）</div>
              </div>
            </div>
            <div class="performance-analyzer-usage-card__item">
              <span class="performance-analyzer-usage-card__step">2</span>
              <div>
                <div class="performance-analyzer-usage-card__title">粘贴数据</div>
                <div class="helper-text">将数据粘贴到左侧文本区域</div>
              </div>
            </div>
            <div class="performance-analyzer-usage-card__item">
              <span class="performance-analyzer-usage-card__step">3</span>
              <div>
                <div class="performance-analyzer-usage-card__title">调整设置</div>
                <div class="helper-text">选择时间格式；收益率列自动识别</div>
              </div>
            </div>
            <div class="performance-analyzer-usage-card__item">
              <span class="performance-analyzer-usage-card__step">4</span>
              <div>
                <div class="performance-analyzer-usage-card__title">开始分析</div>
                <div class="helper-text">点击按钮查看分析结果</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 核心指标 -->
    <el-row :gutter="12" class="performance-analyzer-metric-grid">
      <el-col :xs="12" :sm="6" class="performance-analyzer-metric-grid__col">
        <el-card shadow="never" class="metric-card--center performance-analyzer-metric-card performance-analyzer-metric-card--primary">
          <div class="card-grid-note">累计收益率</div>
          <div class="performance-analyzer-metric-grid__value">{{ totalReturnText }}</div>
          <div class="helper-text">按最新净值计算</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-metric-grid__col">
        <el-card shadow="never" class="metric-card--center performance-analyzer-metric-card performance-analyzer-metric-card--success">
          <div class="card-grid-note">最新年度收益率</div>
          <div class="performance-analyzer-metric-grid__value">{{ annualReturnText }}</div>
          <div class="helper-text">最新年度区间收益</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-metric-grid__col">
        <el-card shadow="never" class="metric-card--center performance-analyzer-metric-card performance-analyzer-metric-card--danger">
          <div class="card-grid-note">最大回撤</div>
          <div class="performance-analyzer-metric-grid__value">{{ maxDrawdownText }}</div>
          <div class="helper-text">风险指标</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6" class="performance-analyzer-metric-grid__col">
        <el-card shadow="never" class="metric-card--center performance-analyzer-metric-card performance-analyzer-metric-card--warning">
          <div class="card-grid-note">夏普比率</div>
          <div class="performance-analyzer-metric-grid__value">{{ sharpeRatioText }}</div>
          <div class="helper-text">风险调整后收益</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据分析图表 -->
    <el-card v-if="analysisResult" shadow="never" class="section-card">
      <div class="section-label">数据分析图表</div>
      <el-row :gutter="12">
        <el-col :xs="24" :lg="12" class="performance-analyzer-chart-col">
          <el-card shadow="never">
            <div class="performance-analyzer-chart-title">收益率曲线</div>
            <div class="performance-analyzer-chart-box"><canvas ref="returnChartRef"></canvas></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-chart-col">
          <el-card shadow="never">
            <div class="performance-analyzer-chart-title">最大回撤</div>
            <div class="performance-analyzer-chart-box"><canvas ref="drawdownChartRef"></canvas></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-chart-col">
          <el-card shadow="never">
            <div class="performance-analyzer-chart-title">夏普率（过去期间）</div>
            <div class="performance-analyzer-chart-box"><canvas ref="sharpePastChartRef"></canvas></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="performance-analyzer-chart-col">
          <el-card shadow="never">
            <div class="performance-analyzer-chart-title">夏普率（按年度）</div>
            <div class="performance-analyzer-chart-box"><canvas ref="sharpeYearChartRef"></canvas></div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 高级分析结果 -->
    <el-card v-if="analysisResult" shadow="never" class="section-card">
      <el-tabs v-model="activeDetailTab">
        <el-tab-pane label="最大回撤" name="drawdown">
          <el-table :data="drawdownRows" stripe size="small" max-height="420">
            <el-table-column prop="date" label="日期(年度最大回测当日)" min-width="170" />
            <el-table-column prop="year" label="年份" width="90" />
            <el-table-column label="年度回撤" min-width="140">
              <template #default="{ row }">
                <span :class="row.drawdown >= 0 ? 'text-danger' : 'text-success'">
                  {{ isDual ? '模型 ' : '' }}{{ formatPercent(row.drawdown) }}
                </span>
                <div v-if="row.indexDrawdown !== null" class="performance-analyzer-sub-line">指数 {{ formatPercent(row.indexDrawdown) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="累计收益率" min-width="130">
              <template #default="{ row }">
                {{ formatNumber(row.dailyReturn, 2) }}%
                <div v-if="row.indexDailyReturn !== null" class="performance-analyzer-sub-line">指数 {{ formatNumber(row.indexDailyReturn, 2) }}%</div>
              </template>
            </el-table-column>
            <el-table-column label="净值" min-width="110">
              <template #default="{ row }">
                {{ formatNumber(row.netValue) }}
                <div v-if="row.indexNetValue !== null" class="performance-analyzer-sub-line">指数 {{ formatNumber(row.indexNetValue) }}</div>
              </template>
            </el-table-column>
            <template #empty>没有可用的回撤数据</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="收益率分析" name="returns">
          <el-table :data="returnsRows" stripe size="small" max-height="420">
            <el-table-column prop="date" label="日期" min-width="120" />
            <el-table-column prop="year" label="年份" width="90" />
            <el-table-column label="年度收益率" min-width="130">
              <template #default="{ row }">
                <span :class="getReturnRateValue(row) >= 0 ? 'text-success' : 'text-danger'">
                  {{ formatPercent(getReturnRateValue(row)) }}
                </span>
                <div v-if="row.indexReturn !== null" class="performance-analyzer-sub-line">指数 {{ formatPercent(row.indexReturn) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="净值" min-width="100">
              <template #default="{ row }">{{ formatNumber(row.netValue) }}</template>
            </el-table-column>
            <template #empty>没有可用的收益率数据</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="夏普比率" name="sharpe">
          <el-table :data="sharpeRows" stripe size="small" max-height="420">
            <el-table-column prop="label" label="时间段" min-width="140" />
            <el-table-column label="夏普比率" min-width="110">
              <template #default="{ row }">
                {{ formatNumber(row.sharpe) }}
                <div v-if="row.indexSharpe !== null" class="performance-analyzer-sub-line">指数 {{ formatNumber(row.indexSharpe) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="平均月收益率" min-width="120">
              <template #default="{ row }">
                {{ formatPercent(row.avgMonthlyReturn) }}
                <div v-if="row.indexAvgMonthlyReturn !== null" class="performance-analyzer-sub-line">指数 {{ formatPercent(row.indexAvgMonthlyReturn) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="月波动率" min-width="110">
              <template #default="{ row }">
                {{ formatPercent(row.monthlyStdDev) }}
                <div v-if="row.indexMonthlyStdDev !== null" class="performance-analyzer-sub-line">指数 {{ formatPercent(row.indexMonthlyStdDev) }}</div>
              </template>
            </el-table-column>
            <el-table-column label="年化波动率" min-width="110">
              <template #default="{ row }">
                {{ formatPercent(row.annualStdDev) }}
                <div v-if="row.indexAnnualStdDev !== null" class="performance-analyzer-sub-line">指数 {{ formatPercent(row.indexAnnualStdDev) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="startDate" label="开始日期" width="100" />
            <el-table-column prop="endDate" label="结束日期" width="100" />
            <template #empty>没有可用的夏普比率数据</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 导出结果模态框 -->
    <el-dialog v-model="exportModalVisible" title="导出分析结果" width="720px">
      <el-input
        :model-value="exportJsonText"
        type="textarea"
        :rows="15"
        readonly
        class="performance-analyzer-export-textarea"
      />
      <template #footer>
        <el-button @click="exportModalVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyExportJson">复制到剪贴板</el-button>
        <el-button type="success" @click="downloadExportJson">下载JSON文件</el-button>
      </template>
    </el-dialog>

    <!-- 加载提示 -->
    <div v-if="loading" class="performance-analyzer-loading-overlay">
      <span class="performance-analyzer-loading-overlay__spinner" aria-hidden="true"></span>
      <div class="performance-analyzer-loading-overlay__text">计算中，请稍候...</div>
      <el-button @click="cancelLoading">取消</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { analyzePerformanceAnalysis } from '@/api/performance_analysis'
import { useChartJs } from '@/composables/useChartJs'

const { loadChartJs } = useChartJs()

// ── state ────────────────────────────────────────────────────
const dataInput = ref('')
const timeFormat = ref('auto')
const analyzing = ref(false)
const loading = ref(false)
// API 返回的 results 本体（单列：maximum_drawdown/returns_rate/sharpe_ratios；
// 三列双模式：start_* / index_* 前缀字段 + analysis_mode='dual'）
const analysisResult = ref(null)
// 导出用：保存接口原始 results（与静态版 currentResults 一致）
const currentResults = ref(null)
const rawData = ref([])
const exportModalVisible = ref(false)
const activeDetailTab = ref('drawdown')

let abortController = null
let abortReason = '' // 'cancel' | 'timeout'
let timeoutId = null

const lineCount = computed(() => rawData.value.length)

// ── 结果解包（静态版 js:51-98 原样翻译）─────────────────────
function formatPercent(value, digits = 2) {
  if (value === undefined || value === null || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(digits)}%` : '-'
}

function formatNumber(value, digits = 4) {
  if (value === undefined || value === null || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '-'
}

function getReturnRateValue(item) {
  return item?.annual_return ?? item?.monthly_return ?? item?.daily_return ?? item?.return
}

function isDualResults(results) {
  return results?.analysis_mode === 'dual'
    || Boolean(results?.start_returns_rate || results?.index_returns_rate)
}

function getPrimaryResults(results) {
  if (!isDualResults(results)) return results
  return {
    maximum_drawdown: results.start_maximum_drawdown,
    returns_rate: results.start_returns_rate,
    sharpe_ratios: results.start_sharpe_ratios,
    analysis_mode: results.analysis_mode,
  }
}

function getSecondaryResults(results) {
  if (!isDualResults(results)) return null
  return {
    maximum_drawdown: results.index_maximum_drawdown,
    returns_rate: results.index_returns_rate,
    sharpe_ratios: results.index_sharpe_ratios,
    analysis_mode: results.analysis_mode,
  }
}

function formatSharpePeriodLabel(key) {
  if (key === 'all') return '全部'
  const pastMatch = key.match(/^past_(\d+)_years_since_(\d{4})$/)
  if (pastMatch) return `近${pastMatch[1]}年（${pastMatch[2]}起）`
  const yearMatch = key.match(/^year_(\d+)_(\d{4})$/)
  if (yearMatch) return `第${yearMatch[1]}年（${yearMatch[2]}）`
  return key
}

const isDual = computed(() => (analysisResult.value ? isDualResults(analysisResult.value) : false))
const primaryResults = computed(() => (analysisResult.value ? getPrimaryResults(analysisResult.value) : null))

// ── 核心指标（静态版 updateMetrics）─────────────────────────
const totalReturnText = computed(() => {
  const primary = primaryResults.value
  const list = primary?.returns_rate
  if (!Array.isArray(list) || !list.length) return '-'
  const latest = list[list.length - 1]
  const totalReturn = latest?.net_value !== undefined ? latest.net_value - 1 : getReturnRateValue(latest)
  return `${formatNumber(totalReturn, 2)}%`
})

const annualReturnText = computed(() => {
  const primary = primaryResults.value
  const list = primary?.returns_rate
  if (!Array.isArray(list) || !list.length) return '-'
  return formatPercent(list[list.length - 1]?.annual_return)
})

const maxDrawdownText = computed(() => {
  const primary = primaryResults.value
  if (primary?.maximum_drawdown === undefined) return '-'
  return formatPercent(primary.maximum_drawdown?.total_maximum_drawdown?.drawdown)
})

const sharpeRatioText = computed(() => {
  const primary = primaryResults.value
  if (primary?.sharpe_ratios === undefined) return '-'
  return formatNumber(primary.sharpe_ratios?.all?.sharpe_ratio)
})

// ── 明细表（静态版 updateDrawdownTable / updateReturnsData / updateSharpeTable）───
const drawdownRows = computed(() => {
  const primary = primaryResults.value
  const secondary = analysisResult.value ? getSecondaryResults(analysisResult.value) : null
  const list = primary?.maximum_drawdown?.year_maximum_drawdown
  if (!Array.isArray(list)) return []
  return list.map((item, index) => {
    const s = secondary?.maximum_drawdown?.year_maximum_drawdown?.[index]
    return {
      date: item.date,
      year: item.year,
      drawdown: item.drawdown,
      indexDrawdown: s ? s.drawdown : null,
      dailyReturn: item.daily_return,
      indexDailyReturn: s ? s.daily_return : null,
      netValue: item.net_value,
      indexNetValue: s ? s.net_value : null,
    }
  })
})

const returnsRows = computed(() => {
  const primary = primaryResults.value
  const secondary = analysisResult.value ? getSecondaryResults(analysisResult.value) : null
  const list = primary?.returns_rate
  if (!Array.isArray(list)) return []
  return list.map((item, index) => {
    const s = secondary?.returns_rate?.[index]
    return {
      date: item.date,
      year: item.year,
      return: getReturnRateValue(item),
      indexReturn: s ? getReturnRateValue(s) : null,
      netValue: item.net_value,
    }
  })
})

const sharpeRows = computed(() => {
  const primary = primaryResults.value
  const secondary = analysisResult.value ? getSecondaryResults(analysisResult.value) : null
  const ratios = primary?.sharpe_ratios
  if (!ratios || typeof ratios !== 'object') return []
  return Object.entries(ratios)
    .filter(([, value]) => value !== null && typeof value === 'object')
    .map(([key, value]) => {
      const s = secondary?.sharpe_ratios?.[key]
      return {
        label: formatSharpePeriodLabel(key),
        sharpe: value.sharpe_ratio,
        avgMonthlyReturn: value.avg_monthly_return,
        monthlyStdDev: value.monthly_std_dev,
        annualStdDev: value.annual_std_dev,
        startDate: value.start_date || '-',
        endDate: value.end_date || '-',
        indexSharpe: s ? s.sharpe_ratio : null,
        indexAvgMonthlyReturn: s ? s.avg_monthly_return : null,
        indexMonthlyStdDev: s ? s.monthly_std_dev : null,
        indexAnnualStdDev: s ? s.annual_std_dev : null,
      }
    })
})

// ── 输入辅助 ────────────────────────────────────────────────
async function pasteFromClipboard() {
  try {
    dataInput.value = await navigator.clipboard.readText()
    ElMessage.success('已从剪贴板粘贴数据')
  } catch {
    ElMessage.warning('无法访问剪贴板，请手动粘贴')
  }
}

function loadSampleData() {
  dataInput.value = `2025-01-01 0.0234
2025-01-02 -0.0156
2025-01-03 0.0089
2025-01-04 0.0123
2025-01-05 -0.0078
2025-01-06 0.0189
2025-01-07 -0.0056
2025-01-08 0.0098
2025-01-09 0.0145
2025-01-10 -0.0032`
  ElMessage.info('已加载示例数据')
}

let clearConfirmVisible = false
async function clearAllData() {
  // Esc 触发时同一次按键也会被 MessageBox 自身接收，防止重复弹确认框
  if (clearConfirmVisible) return
  clearConfirmVisible = true
  try {
    await ElMessageBox.confirm('确定要清空所有数据吗？此操作不可恢复。', '提示', { type: 'warning' })
  } catch {
    return
  } finally {
    clearConfirmVisible = false
  }
  dataInput.value = ''
  analysisResult.value = null
  currentResults.value = null
  rawData.value = []
  destroyAllCharts()
  ElMessage.success('已清空所有数据')
}

// ── 分析（POST /performance_analysis/analyze，静态版 parseExcelData）───
function isRequestCanceled(error) {
  return error?.name === 'AbortError'
    || error?.name === 'CanceledError'
    || error?.code === 'ERR_CANCELED'
    || error?.cause?.name === 'CanceledError'
    || error?.cause?.code === 'ERR_CANCELED'
}

async function analyze() {
  if (analyzing.value) return
  const inputText = dataInput.value.trim()
  if (!inputText) {
    ElMessage.warning('请输入要分析的数据')
    return
  }
  const nonEmptyLines = inputText.split('\n').filter((line) => line.trim().length > 0)
  if (!nonEmptyLines.length) {
    ElMessage.warning('请输入有效的分析数据')
    return
  }
  rawData.value = nonEmptyLines

  loading.value = true
  analyzing.value = true
  abortReason = ''
  abortController = new AbortController()
  // 30 秒超时（静态版 js:193-197）；rawApi 请求级超时放宽作为兜底
  timeoutId = setTimeout(() => {
    abortReason = 'timeout'
    abortController?.abort()
  }, 30000)

  try {
    // 拦截器已深解包：信封 data 为 { results, metrics }，results 才是指标本体
    const payload = await analyzePerformanceAnalysis(
      { data: inputText, time_format: timeFormat.value },
      { signal: abortController.signal, timeout: 45000 },
    )
    const results = payload?.results ?? payload
    if (!results || typeof results !== 'object' || Array.isArray(results)) {
      throw new Error('后端未返回分析结果')
    }
    currentResults.value = { results }
    analysisResult.value = results
    ElMessage.success('数据分析完成')
    await nextTick()
    renderCharts(results)
  } catch (error) {
    if (isRequestCanceled(error)) {
      ElMessage.info(abortReason === 'timeout' ? '请求超时，请稍后重试' : '已取消操作')
    } else {
      ElMessage.error('请求出错: ' + (error?.message || '未知错误'))
    }
  } finally {
    clearTimeout(timeoutId)
    timeoutId = null
    abortController = null
    loading.value = false
    analyzing.value = false
  }
}

function refreshData() {
  if (rawData.value.length > 0) {
    analyze()
  } else {
    ElMessage.warning('没有可刷新的数据')
  }
}

function cancelLoading() {
  if (abortController) {
    abortReason = 'cancel'
    abortController.abort()
  }
}

// ── 导出（静态版 exportResults / copyToClipboard / downloadJSON）───
const exportJsonText = computed(() => {
  if (!currentResults.value) return ''
  return JSON.stringify(
    {
      meta: {
        generatedAt: new Date().toISOString(),
        dataPoints: rawData.value.length,
      },
      results: currentResults.value.results,
    },
    null,
    2,
  )
})

function openExportModal() {
  if (!currentResults.value) {
    ElMessage.warning('没有可导出的结果')
    return
  }
  exportModalVisible.value = true
}

async function copyExportJson() {
  try {
    await navigator.clipboard.writeText(exportJsonText.value)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败: ' + (error?.message || '未知错误'))
  }
}

function downloadExportJson() {
  const blob = new Blob([exportJsonText.value], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── 键盘快捷键（Ctrl+Enter 分析、Esc 清空）──────────────────
function onKeyDown(event) {
  if (event.ctrlKey && event.key === 'Enter') {
    event.preventDefault()
    analyze()
    return
  }
  if (event.key === 'Escape') {
    clearAllData()
  }
}

// ── 图表（Chart.js，复用 useChartJs + V2 页同模式）──────────
const returnChartRef = ref(null)
const drawdownChartRef = ref(null)
const sharpePastChartRef = ref(null)
const sharpeYearChartRef = ref(null)

const chartInstances = {}

function chartTheme() {
  if (typeof window === 'undefined' || !window.getComputedStyle) {
    return { textColor: '#48658d', mutedColor: '#6c84a5', gridColor: 'rgba(30, 64, 175, 0.12)' }
  }
  const styles = getComputedStyle(document.documentElement)
  const read = (name, fallback) => (styles.getPropertyValue(name) || '').trim() || fallback
  return {
    textColor: read('--app-text-soft', '#48658d'),
    mutedColor: read('--app-text-muted', '#6c84a5'),
    gridColor: read('--app-border', 'rgba(30, 64, 175, 0.12)'),
  }
}

function baseChartOptions({ yTitle = null, xTitle = null, yOpts = {}, xOpts = {} } = {}) {
  const theme = chartTheme()
  const axis = (title, extra = {}) => {
    const { ticks, ...rest } = extra
    return {
      title: { display: Boolean(title), text: title || undefined, color: theme.mutedColor },
      ticks: { color: theme.textColor, ...(ticks || {}) },
      grid: { color: theme.gridColor },
      ...rest,
    }
  }
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: theme.textColor } } },
    scales: { x: axis(xTitle, xOpts), y: axis(yTitle, yOpts) },
  }
}

function destroyChart(key) {
  if (chartInstances[key]) {
    try {
      chartInstances[key].destroy()
    } catch {}
    chartInstances[key] = null
  }
}

function buildChart(Chart, canvasRef, key, type, labels, datasets, options = {}) {
  const el = canvasRef.value
  if (!el) return
  destroyChart(key)
  chartInstances[key] = new Chart(el, {
    type,
    data: { labels, datasets },
    options,
  })
}

function destroyAllCharts() {
  Object.keys(chartInstances).forEach(destroyChart)
}

async function renderCharts(results) {
  let Chart
  try {
    Chart = await loadChartJs()
  } catch {
    return
  }
  renderMainReturnsChart(Chart, results)
  renderDrawdownChart(Chart, results)
  renderSharpePastChart(Chart, results)
  renderSharpeYearChart(Chart, results)
}

// 收益率曲线（静态版 updateMainReturnsChart：模型/指数双数据集）
function renderMainReturnsChart(Chart, results) {
  const primary = getPrimaryResults(results)
  const secondary = getSecondaryResults(results)
  const returnsData = primary?.returns_rate
  if (!Array.isArray(returnsData)) return

  const labels = returnsData.map((item) => {
    const date = new Date(item.date)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  })
  const datasets = [{
    label: isDualResults(results) ? '模型年度收益率 (%)' : '年度收益率 (%)',
    data: returnsData.map((item) => getReturnRateValue(item) * 100),
    borderColor: '#007bff',
    backgroundColor: 'rgba(0, 123, 255, 0.1)',
    borderWidth: 2,
    fill: true,
    tension: 0.1,
  }]
  if (secondary?.returns_rate) {
    datasets.push({
      label: '指数年度收益率 (%)',
      data: secondary.returns_rate.map((item) => getReturnRateValue(item) * 100),
      borderColor: '#6c757d',
      backgroundColor: 'rgba(108, 117, 125, 0.08)',
      borderWidth: 2,
      fill: false,
      tension: 0.1,
    })
  }
  buildChart(Chart, returnChartRef, 'return', 'line', labels, datasets, baseChartOptions({
    yTitle: '收益率 (%)',
    xTitle: '日期',
    yOpts: {
      beginAtZero: true,
      ticks: { callback: (value) => value + '%' },
    },
  }))
}

// 最大回撤（静态版 updateDrawdownChart）
function renderDrawdownChart(Chart, results) {
  const primary = getPrimaryResults(results)
  const secondary = getSecondaryResults(results)
  const drawdownData = primary?.maximum_drawdown?.year_maximum_drawdown
  if (!Array.isArray(drawdownData)) return

  const labels = drawdownData.map((item) => item.year)
  const datasets = [{
    label: isDualResults(results) ? '模型最大回撤 (%)' : '最大回撤 (%)',
    data: drawdownData.map((item) => item.drawdown * 100),
    borderColor: '#dc3545',
    backgroundColor: 'rgba(220, 53, 69, 0.1)',
    borderWidth: 2,
    fill: true,
    tension: 0.1,
  }]
  if (secondary?.maximum_drawdown?.year_maximum_drawdown) {
    datasets.push({
      label: '指数最大回撤 (%)',
      data: secondary.maximum_drawdown.year_maximum_drawdown.map((item) => item.drawdown * 100),
      borderColor: '#6c757d',
      backgroundColor: 'rgba(108, 117, 125, 0.08)',
      borderWidth: 2,
      fill: false,
      tension: 0.1,
    })
  }
  buildChart(Chart, drawdownChartRef, 'drawdown', 'line', labels, datasets, baseChartOptions({
    yTitle: '回撤 (%)',
    xTitle: '年份',
    yOpts: { beginAtZero: true },
  }))
}

// 夏普率（过去期间，past_*；>=1 绿色，否则黄色）（静态版 updateSharpePastChart）
function renderSharpePastChart(Chart, results) {
  renderSharpeBarChart(Chart, results, sharpePastChartRef, 'sharpePast', 'past_', {
    above: { background: 'rgba(40, 167, 69, 0.5)', border: '#28a745' },
    below: { background: 'rgba(255, 193, 7, 0.5)', border: '#ffc107' },
  })
}

// 夏普率（按年度，year_*；>=1 绿色，否则红色）（静态版 updateSharpeYearChart）
function renderSharpeYearChart(Chart, results) {
  renderSharpeBarChart(Chart, results, sharpeYearChartRef, 'sharpeYear', 'year_', {
    above: { background: 'rgba(40, 167, 69, 0.5)', border: '#28a745' },
    below: { background: 'rgba(220, 53, 69, 0.5)', border: '#dc3545' },
  })
}

function renderSharpeBarChart(Chart, results, canvasRef, key, keyword, colors) {
  const primary = getPrimaryResults(results)
  const secondary = getSecondaryResults(results)
  const ratios = primary?.sharpe_ratios
  if (!ratios || typeof ratios !== 'object') return

  const periodData = Object.entries(ratios)
    .filter(([k]) => k.includes(keyword))
    .map(([k, value]) => ({
      key: k,
      label: formatSharpePeriodLabel(k),
      sharpe: value.sharpe_ratio,
    }))

  const labels = periodData.map((item) => item.label)
  const sharpeValues = periodData.map((item) => item.sharpe)
  const datasets = [{
    label: isDualResults(results) ? '模型夏普比率' : '夏普比率',
    data: sharpeValues,
    backgroundColor: sharpeValues.map((value) => (value >= 1 ? colors.above.background : colors.below.background)),
    borderColor: sharpeValues.map((value) => (value >= 1 ? colors.above.border : colors.below.border)),
    borderWidth: 1,
  }]
  if (secondary?.sharpe_ratios) {
    datasets.push({
      label: '指数夏普比率',
      data: periodData.map((item) => secondary.sharpe_ratios[item.key]?.sharpe_ratio ?? null),
      backgroundColor: 'rgba(108, 117, 125, 0.35)',
      borderColor: '#6c757d',
      borderWidth: 1,
    })
  }
  buildChart(Chart, canvasRef, key, 'bar', labels, datasets, baseChartOptions({
    yTitle: '夏普比率',
    yOpts: { beginAtZero: true },
  }))
}

// ── 生命周期 ─────────────────────────────────────────────────
onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  clearTimeout(timeoutId)
  abortController?.abort()
  destroyAllCharts()
})
</script>

<style scoped>
.performance-analyzer-input-panel {
  padding: 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.74);
}

.performance-analyzer-input-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.performance-analyzer-input-panel__title {
  margin: 0;
}

.performance-analyzer-input-panel__textarea :deep(textarea) {
  font-family: 'Fira Code', monospace;
}

.performance-analyzer-input-panel__count {
  margin-top: 4px;
  text-align: right;
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.performance-analyzer-input-panel__hint {
  margin-bottom: 12px;
}

.performance-analyzer-fill-card {
  height: 100%;
}

.performance-analyzer-usage-card__item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.performance-analyzer-usage-card__step {
  flex: 0 0 22px;
  height: 22px;
  line-height: 22px;
  border-radius: 50%;
  text-align: center;
  color: #fff;
  background: var(--el-color-primary);
  font-size: var(--app-font-xs, 12px);
  font-weight: 600;
}

.performance-analyzer-usage-card__title {
  font-weight: 600;
  margin-bottom: 2px;
}

.performance-analyzer-metric-grid {
  margin-bottom: 16px;
}

.performance-analyzer-metric-grid__col {
  margin-bottom: 12px;
}

.performance-analyzer-metric-card {
  text-align: center;
}

.performance-analyzer-metric-card--primary {
  border-color: var(--el-color-primary);
}

.performance-analyzer-metric-card--success {
  border-color: var(--el-color-success);
}

.performance-analyzer-metric-card--danger {
  border-color: var(--el-color-danger);
}

.performance-analyzer-metric-card--warning {
  border-color: var(--el-color-warning);
}

.performance-analyzer-metric-grid__value {
  margin: 4px 0;
  font-size: 22px;
  font-weight: 700;
}

.performance-analyzer-chart-col {
  margin-bottom: 12px;
}

.performance-analyzer-chart-title {
  margin-bottom: 8px;
  font-size: var(--app-font-sm);
  font-weight: 700;
}

.performance-analyzer-chart-box {
  height: 300px;
}

.performance-analyzer-sub-line {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.performance-analyzer-export-textarea :deep(textarea) {
  font-family: 'Courier New', monospace;
}

.performance-analyzer-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.75);
}

.performance-analyzer-loading-overlay__spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(255, 255, 255, 0.25);
  border-top-color: var(--el-color-primary);
  border-radius: 50%;
  animation: performance-analyzer-loading-spin 1s linear infinite;
}

.performance-analyzer-loading-overlay__text {
  color: #fff;
  font-size: var(--app-font-md, 16px);
}

@keyframes performance-analyzer-loading-spin {
  to {
    transform: rotate(360deg);
  }
}

.text-success {
  color: var(--el-color-success);
}

.text-danger {
  color: var(--el-color-danger);
}

@media (max-width: 767px) {
  .performance-analyzer-input-panel__head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
