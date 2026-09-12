<template>
  <div class="app-page model-summary-page">
    <PageToolbar eyebrow="MODEL SUMMARY" title="单模型汇总数据看板" description="按历史任务结果汇总 C3、C5、回测最优参数结果">
      <template #actions>
        <el-button @click="runSummaryQuery">刷新</el-button>
        <el-button type="success" @click="openExportCsvModal">导出 CSV</el-button>
        <el-button type="primary" :loading="rebuilding" @click="rebuildSummary">重建索引</el-button>
      </template>
    </PageToolbar>

    <!-- 概览卡片 -->
    <el-card shadow="never" class="page-section">
      <div class="summary-grid">
        <div class="summary-market">
          <div class="summary-card-title">市场结构</div>
          <div class="summary-main-row">
            <div class="summary-main-number">{{ summary.stock_count ?? 0 }}</div>
            <div class="summary-main-label">股票总数</div>
          </div>
          <div class="market-share-bar" aria-hidden="true">
            <div class="market-share-cn" :style="{ width: `${cnSharePercent}%` }"></div>
            <div class="market-share-us" :style="{ width: `${usSharePercent}%` }"></div>
          </div>
          <div class="market-inline-row">
            <div class="market-row">
              <span><i class="market-dot cn"></i>A股</span>
              <strong>{{ summary.cn_stock_count ?? 0 }}</strong>
            </div>
            <div class="market-row">
              <span><i class="market-dot us"></i>美股</span>
              <strong>{{ summary.us_stock_count ?? 0 }}</strong>
            </div>
          </div>
          <div class="market-task-row">
            <span>任务总数</span>
            <strong>{{ summary.task_count ?? 0 }}</strong>
          </div>
        </div>
        <div
          v-for="threshold in thresholdCards"
          :key="threshold.key"
          class="return-threshold-card"
        >
          <div class="return-card-title">ReturnBeats</div>
          <div class="return-card-threshold">&gt; {{ threshold.value }}%</div>
          <div class="return-card-count">{{ summary[threshold.countKey] ?? 0 }}</div>
          <el-progress
            :percentage="thresholdRates[threshold.key]"
            :stroke-width="8"
            :show-text="false"
          />
          <div class="return-card-caption">
            {{ returnRateCaption }} {{ thresholdRates[threshold.key].toFixed(1) }}%
          </div>
        </div>
      </div>
    </el-card>

    <!-- 筛选表单 -->
    <el-card shadow="never" class="page-section">
      <el-form :inline="true" class="summary-filter-form" @submit.prevent="onSearch">
        <el-form-item label="任务类型">
          <el-select v-model="filters.taskType" style="width: 120px" clearable>
            <el-option label="C3" value="google_sheet" />
            <el-option label="C5" value="google_sheet_C5" />
            <el-option label="回测" value="backtest_training" />
          </el-select>
        </el-form-item>
        <el-form-item label="股票代码">
          <el-input v-model="filters.stockCode" placeholder="代码/股票名/任务名" style="width: 180px" clearable />
        </el-form-item>
        <el-form-item label="市场">
          <el-select v-model="filters.marketType" style="width: 100px" clearable>
            <el-option label="A股" value="cn" />
            <el-option label="美股" value="us" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果日期范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item label="年份/区间">
          <el-select v-model="filters.periodFilter" style="width: 110px" clearable>
            <el-option v-for="option in periodOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务 ID">
          <el-input v-model="filters.taskId" placeholder="精确任务 ID" style="width: 170px" clearable />
        </el-form-item>
        <el-form-item label="结果 ID">
          <el-input v-model.number="filters.resultId" placeholder="结果 ID" style="width: 120px" clearable />
        </el-form-item>
        <el-form-item label="汇总方式">
          <el-select v-model="filters.summaryType" style="width: 120px">
            <el-option label="任务汇总" value="task" />
            <el-option label="股票汇总" value="stock" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据范围">
          <el-select v-model="filters.bestOnly" style="width: 120px">
            <el-option label="仅最优" value="true" />
            <el-option label="全部结果" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="超额收益">
          <el-select v-model="filters.excessReturnMin" style="width: 120px" clearable>
            <el-option label="大于 0%" value="0" />
            <el-option label="大于 10%" value="10" />
            <el-option label="大于 20%" value="20" />
            <el-option label="大于 30%" value="30" />
            <el-option label="大于 50%" value="50" />
            <el-option label="大于 100%" value="100" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onSearch">查询</el-button>
        </el-form-item>
      </el-form>
      <div class="helper-text">
        全部结果必须输入股票代码、股票名或任务名关键字；市场按股票代码纯数字识别 A股。
      </div>
      <div class="helper-text">
        {{ statusText }}
        <router-link v-if="rebuildTaskId" :to="`/admin/tasks?keyword=${encodeURIComponent(rebuildTaskId)}`">
          查看重建任务日志
        </router-link>
      </div>
    </el-card>

    <!-- 汇总表格 -->
    <el-card shadow="never" class="page-section">
      <el-table v-loading="loading" :data="items" border stripe size="small" class="model-summary-table">
        <el-table-column
          v-for="column in leadingColumns"
          :key="column.key"
          :label="column.label"
          :width="column.width"
          :fixed="column.fixed"
        >
          <template #default="{ row }">
            <template v-if="column.key === 'task_name'">
              <router-link v-if="taskDetailUrl(row)" :to="taskDetailUrl(row)" class="mono-inline">
                {{ row.task_name || row.task_id || '-' }}
              </router-link>
              <span v-else>{{ row.task_name || row.task_id || '-' }}</span>
            </template>
            <template v-else-if="column.key === 'task_type'">
              {{ taskTypeLabel(row.task_type) }}
            </template>
            <template v-else-if="column.key === 'best_metric_value'">
              <span :class="metricClass(row.best_metric_value)">{{ formatMetric(row.best_metric_value, 'percent') }}</span>
            </template>
            <template v-else-if="column.key === 'result_timestamp'">
              {{ formatDateTime(row.result_timestamp) }}
            </template>
            <template v-else>
              {{ row[column.key] || '-' }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="参数" min-width="240">
          <template #default="{ row }">
            <div class="param-tags">
              <el-tag
                v-for="(value, key) in row.parameter_summary"
                v-show="value !== null && value !== undefined && value !== ''"
                :key="key"
                size="small"
                class="param-tag"
              >
                {{ key }}: {{ formatParameterValue(value) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="年份/区间" width="110">
          <template #default="{ row }">{{ row.kline_range || row.year_label || '-' }}</template>
        </el-table-column>
        <el-table-column
          v-for="column in columns"
          :key="column.key"
          :label="column.label"
          min-width="120"
          align="right"
        >
          <template #default="{ row }">
            <span :class="metricClass(row.metrics?.[column.key])">
              {{ formatMetric(row.metrics?.[column.key], column.format) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="结果 ID" width="100" fixed="right">
          <template #default="{ row }">
            <router-link v-if="row.task_id" :to="`/admin/results?task_id=${encodeURIComponent(row.task_id)}`">
              {{ row.task_result_id || '-' }}
            </router-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无汇总数据，请先重建索引或调整筛选条件" />
        </template>
      </el-table>

      <div class="summary-pagination">
        <div class="summary-pagination__meta">
          <span>显示 {{ rangeStart }}-{{ rangeEnd }} 条，共 {{ total }} 条任务</span>
          <el-select v-model="perPage" style="width: 100px" @change="onPageSizeChange">
            <el-option label="25 / 页" :value="25" />
            <el-option label="50 / 页" :value="50" />
            <el-option label="100 / 页" :value="100" />
            <el-option label="200 / 页" :value="200" />
          </el-select>
        </div>
        <el-pagination
          v-model:current-page="page"
          :page-count="pages || 1"
          layout="prev, pager, next"
          @current-change="runSummaryQuery"
        />
      </div>
    </el-card>

    <!-- 导出对话框 -->
    <el-dialog v-model="exportDialogVisible" title="确认导出 CSV" width="480px">
      <el-form label-width="80px">
        <el-form-item label="文件名">
          <el-input ref="exportFilenameInput" v-model="exportFilename" placeholder="请输入 CSV 文件名" />
          <div class="helper-text">无需输入 .csv，系统会自动补全。</div>
        </el-form-item>
      </el-form>
      <div class="helper-text">{{ exportSummaryText }}</div>
      <template #footer>
        <el-button @click="exportDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="exporting" @click="exportSummaryCsv">确认导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getModelSummary, rebuildModelSummary, getModelSummaryRebuildStatus } from '@/api/admin'
import { rawApi } from '@/api'
import { formatDateTime } from '@/utils/format'

const leadingColumns = [
  { key: 'stock_code', label: '产品/股票', width: 130, fixed: 'left' },
  { key: 'stock_name', label: '股票名', width: 120 },
  { key: 'task_name', label: '任务名', width: 200 },
  { key: 'task_type', label: '类型', width: 80 },
  { key: 'best_metric_value', label: 'return beats', width: 110 },
  { key: 'result_timestamp', label: '结果时间', width: 160 },
]

const thresholdCards = [
  { key: 'gt0', value: 0, countKey: 'return_beats_gt_0' },
  { key: 'gt20', value: 20, countKey: 'return_beats_gt_20' },
  { key: 'gt50', value: 50, countKey: 'return_beats_gt_50' },
  { key: 'gt100', value: 100, countKey: 'return_beats_gt_100' },
]

const periodOptions = [
  { value: 'recent_1y', label: '近1年' },
  { value: 'recent_3y', label: '近3年' },
  { value: 'full_2026', label: '整年26' },
  { value: 'full_2025', label: '整年25' },
  { value: 'full_2024', label: '整年24' },
  { value: 'full_2023', label: '整年23' },
  { value: 'full_2022', label: '整年22' },
  { value: 'full_2021', label: '整年21' },
  { value: 'full_2020', label: '整年20' },
  { value: 'full_2019', label: '整年19' },
]

const items = ref([])
const columns = ref([])
const summary = ref({})
const total = ref(0)
const pages = ref(0)
const page = ref(1)
const perPage = ref(50)
const loading = ref(false)
const statusText = ref('')

const filters = reactive({
  summaryType: 'task',
  bestOnly: 'true',
  taskType: '',
  stockCode: '',
  marketType: '',
  periodFilter: '',
  excessReturnMin: '',
  taskId: '',
  resultId: '',
})
const dateRange = ref(null)

const exportDialogVisible = ref(false)
const exportFilename = ref('')
const exportSummaryText = ref('')
const exporting = ref(false)

const rebuilding = ref(false)
const rebuildJobId = ref('')
let rebuildTimer = null

const rebuildTaskId = computed(() => rebuildJobId.value.slice(0, 8))

const cnSharePercent = computed(() => percentOf(summary.value.cn_stock_count))
const usSharePercent = computed(() => percentOf(summary.value.us_stock_count))
const returnRateCaption = computed(() =>
  filters.summaryType === 'stock' ? '占筛选股票' : '占筛选任务'
)

const thresholdRates = computed(() => {
  const base = filters.summaryType === 'stock'
    ? Number(summary.value.stock_count || 0)
    : Number(summary.value.task_count || 0)
  const result = {}
  for (const card of thresholdCards) {
    result[card.key] = percentOf(summary.value[card.countKey], base)
  }
  return result
})

const rangeStart = computed(() => (total.value ? (page.value - 1) * perPage.value + 1 : 0))
const rangeEnd = computed(() => (total.value ? Math.min(page.value * perPage.value, total.value) : 0))

function percentOf(value, base = Number(summary.value.stock_count || 0)) {
  if (!base) return 0
  return Math.max(0, Math.min(100, (Number(value || 0) / base) * 100))
}

function taskTypeLabel(value) {
  return {
    google_sheet: 'C3',
    google_sheet_C4: 'C4',
    google_sheet_C5: 'C5',
    backtest_training: '回测',
  }[value] || value || '-'
}

function periodFilterLabel(value) {
  return periodOptions.find((option) => option.value === value)?.label || ''
}

function formatMetric(value, format) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  if (format === 'percent') return `${(number * 100).toFixed(2)}%`
  if (format === 'integer') return String(Math.round(number))
  return number.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

function metricClass(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return ''
  return number > 0 ? 'metric-positive' : 'metric-negative'
}

function formatParameterValue(value) {
  if (Array.isArray(value)) return value.join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value ?? '')
}

function getTaskVersionFromType(taskType) {
  const normalized = String(taskType || '').trim().toLowerCase()
  if (normalized === 'google_sheet_c4') return 'c4'
  if (normalized === 'google_sheet_c5') return 'c5'
  return ''
}

function taskDetailUrl(item) {
  const taskId = item?.task_id || ''
  if (!taskId) return ''
  const normalized = String(item.task_type || '').trim().toLowerCase()
  if (normalized === 'backtest_training') return `/backtest/${encodeURIComponent(taskId)}`
  return `/task/${encodeURIComponent(taskId)}`
}

function collectFilters() {
  const params = {
    page: page.value,
    per_page: perPage.value,
    summary_type: filters.summaryType,
    best_only: filters.bestOnly,
  }
  if (filters.taskType) params.task_type = filters.taskType
  if (filters.stockCode.trim()) params.stock_code = filters.stockCode.trim()
  if (filters.marketType) params.market_type = filters.marketType
  if (filters.periodFilter) params.period_filter = filters.periodFilter
  if (filters.excessReturnMin !== '' && filters.excessReturnMin !== null) {
    params.excess_return_min = filters.excessReturnMin
  }
  if (filters.taskId.trim()) params.task_id = filters.taskId.trim()
  if (filters.resultId) params.result_id = filters.resultId
  const [from, to] = dateRange.value || []
  if (from) params.result_date_from = from
  if (to) params.result_date_to = to
  return params
}

function safeFilenamePart(value) {
  const text = String(value || '').trim()
  if (!text) return ''
  return text.replace(/[\\/:*?"<>|\r\n\t]+/g, '_').slice(0, 80)
}

function defaultExportFilename() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return [
    filters.summaryType === 'stock' ? '股票汇总' : '任务汇总',
    filters.bestOnly === 'false' ? '全部结果' : '仅最优',
    filters.taskType ? taskTypeLabel(filters.taskType) : '全部类型',
    filters.periodFilter ? periodFilterLabel(filters.periodFilter) : '',
    filters.excessReturnMin ? `超额大于${filters.excessReturnMin}` : '',
    filters.stockCode.trim() || filters.taskId.trim() || '全部',
    timestamp,
  ].map(safeFilenamePart).filter(Boolean).join('_')
}

function describeExportFilters() {
  const marketType = filters.marketType === 'cn' ? 'A股' : (filters.marketType === 'us' ? '美股' : '全部市场')
  const periodText = filters.periodFilter ? periodFilterLabel(filters.periodFilter) : '全部'
  const keyword = filters.stockCode.trim() || '未填写'
  const summaryTypeText = filters.summaryType === 'stock' ? '股票汇总' : '任务汇总'
  const rangeText = filters.bestOnly === 'false' ? '全部结果' : '仅最优'
  const thresholdText = filters.excessReturnMin ? `ReturnBeats > ${filters.excessReturnMin}%` : '全部'
  const [from, to] = dateRange.value || []
  let dateRangeText = ''
  if (from && to) dateRangeText = `；结果日期：${from} 至${to}`
  else if (from) dateRangeText = `；结果日期：≥ ${from}`
  else if (to) dateRangeText = `；结果日期：≤ ${to}`
  return `任务类型：${filters.taskType ? taskTypeLabel(filters.taskType) : '全部'}；市场：${marketType}；年份 / 区间：${periodText}；查询词：${keyword}；汇总方式：${summaryTypeText}；数据范围：${rangeText}；超额收益：${thresholdText}${dateRangeText}`
}

function validateFullQuery() {
  if (filters.bestOnly === 'false' && !filters.stockCode.trim()) {
    throw new Error('查询全部结果时必须输入股票代码、股票名或任务名关键字')
  }
}

async function loadSummary() {
  validateFullQuery()
  loading.value = true
  statusText.value = '加载中...'
  try {
    const payload = (await getModelSummary(collectFilters())) || {}
    columns.value = payload.columns || []
    total.value = payload.pagination?.total || 0
    pages.value = payload.pagination?.pages || 0
    summary.value = payload.summary || {}
    items.value = payload.items || []
    statusText.value = '已加载'
  } catch (error) {
    statusText.value = error.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function runSummaryQuery() {
  loadSummary()
}

function onSearch() {
  page.value = 1
  runSummaryQuery()
}

function onPageSizeChange() {
  page.value = 1
  runSummaryQuery()
}

function openExportCsvModal() {
  try {
    validateFullQuery()
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }
  exportFilename.value = defaultExportFilename()
  exportSummaryText.value = describeExportFilters()
  exportDialogVisible.value = true
}

async function exportSummaryCsv() {
  exporting.value = true
  statusText.value = '正在生成 CSV...'
  try {
    const params = collectFilters()
    if (exportFilename.value.trim()) params.filename = exportFilename.value.trim()
    const blob = await rawApi.get('/api/exports/model-summary', { params, responseType: 'blob' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${exportFilename.value.trim() || 'model_summary'}.csv`
    link.click()
    URL.revokeObjectURL(url)
    exportDialogVisible.value = false
    statusText.value = 'CSV 已开始下载'
  } catch (error) {
    statusText.value = error.message || '导出失败'
    ElMessage.error(error.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function rebuildSummary() {
  try {
    await ElMessageBox.confirm(
      '重建索引会在后台扫描历史 task_results，数据量较大时会慢慢跑。是否继续？',
      '重建索引',
      { type: 'warning' }
    )
  } catch {
    return
  }
  rebuilding.value = true
  statusText.value = '正在启动后台重建...'
  try {
    const data = await rebuildModelSummary({
      task_type: filters.taskType || undefined,
      task_id: filters.taskId.trim() || undefined,
      batch_size: 20,
      reset: true,
    })
    rebuildJobId.value = data.job?.job_id || ''
    statusText.value = `重建任务已创建 ${rebuildJobId.value.slice(0, 8)}`
    pollRebuildStatus()
  } catch (error) {
    statusText.value = error.message || '重建失败'
  } finally {
    rebuilding.value = false
  }
}

async function pollRebuildStatus() {
  if (rebuildTimer) {
    clearTimeout(rebuildTimer)
    rebuildTimer = null
  }
  if (!rebuildJobId.value) return
  try {
    const data = await getModelSummaryRebuildStatus({ job_id: rebuildJobId.value })
    const job = data.job
    if (!job) {
      statusText.value = '暂无重建任务'
      return
    }
    if (job.status === 'completed') {
      const result = job.result || {}
      statusText.value = `重建完成：处理 ${result.processed_tasks || 0} 个任务、${result.processed || 0} 条结果，保留 ${result.indexed || 0} 条，去重 ${result.deduped || 0} 条`
      page.value = 1
      await loadSummary()
      return
    }
    if (job.status === 'error') {
      statusText.value = job.error || '重建失败'
      return
    }
    const task = job.task || {}
    statusText.value = task.total_steps
      ? `后台重建中 ${task.current_step || 0}/${task.total_steps}`
      : `后台重建中 ${rebuildJobId.value.slice(0, 8)}`
    rebuildTimer = setTimeout(pollRebuildStatus, 3000)
  } catch (error) {
    statusText.value = error.message || '重建状态查询失败'
  }
}

onMounted(runSummaryQuery)
onBeforeUnmount(() => {
  if (rebuildTimer) clearTimeout(rebuildTimer)
})
</script>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.summary-market,
.return-threshold-card {
  padding: 16px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface);
}

.summary-card-title,
.return-card-title {
  margin-bottom: 10px;
  color: var(--app-text-soft);
  font-size: var(--app-font-xs);
  font-weight: 600;
}

.summary-main-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.summary-main-number {
  color: var(--app-text);
  font-size: 28px;
  font-weight: 700;
}

.summary-main-label {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.market-share-bar {
  display: flex;
  height: 8px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--app-surface-elevated);
}

.market-share-cn {
  background: #e05a4e;
}

.market-share-us {
  background: #3b6fd4;
}

.market-inline-row {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
}

.market-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--app-text-soft);
  font-size: var(--app-font-xs);
}

.market-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.market-dot.cn {
  background: #e05a4e;
}

.market-dot.us {
  background: #3b6fd4;
}

.market-task-row {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--app-border);
  color: var(--app-text-soft);
  font-size: var(--app-font-xs);
}

.return-card-threshold {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.return-card-count {
  margin: 4px 0 8px;
  color: var(--app-text);
  font-size: 24px;
  font-weight: 700;
}

.return-card-caption {
  margin-top: 6px;
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.summary-filter-form .el-form-item {
  margin-bottom: 10px;
}

.param-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.param-tag {
  max-width: 100%;
}

:deep(.metric-positive) {
  color: #dc2626;
  font-weight: 600;
}

:deep(.metric-negative) {
  color: #16a34a;
  font-weight: 600;
}

.summary-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}

.summary-pagination__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}
</style>
