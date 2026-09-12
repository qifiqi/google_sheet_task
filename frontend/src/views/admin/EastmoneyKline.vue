<template>
  <div class="app-page eastmoney-kline-page">
    <PageToolbar eyebrow="管理后台" title="东方财富K线" />

    <div class="page-section kline-card">
      <el-form
        ref="formRef"
        class="kline-search-form"
        :model="form"
        :rules="rules"
        label-width="auto"
        label-position="left"
        @submit.prevent="submitSearch"
      >
        <el-form-item label="股票查询">
          <el-autocomplete
            v-model="keyword"
            class="stock-autocomplete"
            value-key="displayName"
            placeholder="输入股票代码或名称"
            :fetch-suggestions="querySecurities"
            :debounce="300"
            :trigger-on-focus="false"
            @select="handleSelectStock"
            @blur="handleKeywordBlur"
          />
        </el-form-item>
        <el-form-item label="K线周期">
          <el-select v-model="form.klt">
            <el-option label="日K" value="101" />
            <el-option label="周K" value="102" />
            <el-option label="月K" value="103" />
            <el-option label="1分钟" value="1" />
            <el-option label="5分钟" value="5" />
            <el-option label="15分钟" value="15" />
            <el-option label="30分钟" value="30" />
            <el-option label="60分钟" value="60" />
          </el-select>
        </el-form-item>
        <el-form-item label="条数" prop="lmt">
          <el-input-number v-model="form.lmt" :min="2" :max="10000" :step="1" step-strictly :controls="false" />
        </el-form-item>
        <el-form-item label="复权方式">
          <el-select v-model="form.fqt">
            <el-option label="不复权" value="0" />
            <el-option label="前复权" value="1" />
            <el-option label="后复权" value="2" />
          </el-select>
        </el-form-item>
        <el-button
          type="primary"
          class="kline-submit"
          :icon="Search"
          :loading="submitting"
          @click="submitSearch"
        >
          拉取K线
        </el-button>
      </el-form>
    </div>

    <div v-if="hasAnalysis" class="page-section kline-card">
      <div class="analysis-header">
        <span class="analysis-title">股票波动率分析</span>
        <div class="analysis-controls">
          <div class="analysis-basis">
            <span class="analysis-label">计算价格：</span>
            <el-select v-model="priceBasis" class="price-basis-select" @change="refreshVolatilityAnalysis">
              <el-option v-for="(item, key) in volatilityPriceBases" :key="key" :label="item.label" :value="key" />
            </el-select>
          </div>
          <div class="analysis-basis">
            <span class="analysis-label">计算基准日期：</span>
            <el-date-picker
              v-model="referenceDate"
              class="reference-date-picker"
              type="date"
              value-format="YYYY-MM-DD"
              :editable="false"
              :clearable="false"
              @change="refreshVolatilityAnalysis"
            />
          </div>
        </div>
      </div>

      <div class="analysis-summary">
        <button type="button" class="analysis-copy-block" title="点击复制股票代码" @click="copyText(stockCode)">
          <span>股票代码</span>
          <strong>{{ stockCode }}</strong>
        </button>
        <button type="button" class="analysis-copy-block" title="点击复制股票名称" @click="copyText(stockName)">
          <span>股票名称</span>
          <strong>{{ stockName }}</strong>
        </button>
        <button
          type="button"
          class="analysis-reference"
          title="点击复制参考日期"
          @click="copyText(referenceDateText)"
        >
          参考日期：{{ referenceDateText }}
        </button>
      </div>

      <div class="volatility-comparison-wrap">
        <table class="volatility-comparison">
          <thead>
            <tr>
              <th>指标</th>
              <th>半年</th>
              <th>1年</th>
              <th>2年</th>
              <th>3年</th>
              <th>4年</th>
              <th>5年</th>
              <th>6年</th>
              <th>7年</th>
              <th>汇总</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="volatility-row-label">近年</td>
              <td
                v-for="(item, index) in recentValues"
                :key="'recent-' + index"
                :title="volatilityCellTitle(item, '数据跨度不足')"
              >
                <strong>{{ item.result ? formatPercent(item.result.value) : '-' }}</strong>
              </td>
            </tr>
            <tr>
              <td class="volatility-row-label">年度</td>
              <td
                v-for="(item, index) in yearlyDisplayValues"
                :key="'yearly-' + index"
                :title="volatilityCellTitle(item, '数据不足（至少200条）')"
              >
                <strong>{{ item.result ? formatPercent(item.result.value) : '-' }}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="average-turnover-analysis">
        <div class="average-turnover-header">
          <span>平均成交额分析</span>
          <small>按计算基准日期分段计算</small>
        </div>
        <div class="volatility-comparison-wrap">
          <table class="volatility-comparison">
            <thead>
              <tr>
                <th>指标</th>
                <th>第1年</th>
                <th>第2年</th>
                <th>第3年</th>
                <th>第4年</th>
                <th>第5年</th>
                <th>第6年</th>
                <th>第7年</th>
                <th>总体</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="volatility-row-label">平均成交额</td>
                <td
                  v-for="(item, index) in turnoverValues"
                  :key="'turnover-' + index"
                  :title="turnoverCellTitle(item)"
                >
                  <strong>{{ item.result ? formatAmountValue(item.result.value) : '-' }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="page-section kline-card">
      <div class="table-header">
        <span class="table-title">
          东方财富K线数据
          <small v-if="klineRows.length" class="table-meta">{{ tableMeta }}</small>
        </span>
        <span class="table-operate">
          <el-input
            v-model="exportFileName"
            class="export-file-name"
            placeholder="自定义导出文件名"
            aria-label="导出文件名"
          />
          <span class="export-date-order">
            <span class="analysis-label">导出日期：</span>
            <el-select v-model="exportDateOrder" class="export-order-select">
              <el-option label="日期升序" value="asc" />
              <el-option label="日期降序" value="desc" />
            </el-select>
          </span>
          <el-button :icon="Download" :disabled="exportDisabled" :loading="exporting" @click="handleExport">
            导出Excel
          </el-button>
        </span>
      </div>

      <el-table :data="displayRows" stripe>
        <el-table-column prop="stock_date" label="日期" width="160" fixed="left" />
        <el-table-column label="股票代码" width="120">
          <template #default>{{ stockCode }}</template>
        </el-table-column>
        <el-table-column label="开盘" width="100">
          <template #default="{ row }">{{ formatNumber(row.open, 2) }}</template>
        </el-table-column>
        <el-table-column label="收盘" width="100">
          <template #default="{ row }">{{ formatNumber(row.close, 2) }}</template>
        </el-table-column>
        <el-table-column label="最高" width="100">
          <template #default="{ row }">{{ formatNumber(row.high, 2) }}</template>
        </el-table-column>
        <el-table-column label="最低" width="100">
          <template #default="{ row }">{{ formatNumber(row.low, 2) }}</template>
        </el-table-column>
        <el-table-column label="成交量" width="120">
          <template #default="{ row }">{{ row.volume_raw.toLocaleString('en-US') }}</template>
        </el-table-column>
        <el-table-column label="成交额" width="150">
          <template #default="{ row }">{{ row.amount.toLocaleString('en-US') }}</template>
        </el-table-column>
        <el-table-column label="振幅%" width="90">
          <template #default="{ row }">{{ formatNumber(row.amplitude, 2) }}</template>
        </el-table-column>
        <el-table-column label="涨跌幅%" width="100">
          <template #default="{ row }">{{ formatNumber(row.pct_change, 2) }}</template>
        </el-table-column>
        <el-table-column label="换手率%" width="100">
          <template #default="{ row }">{{ formatNumber(row.turnover_rate, 2) }}</template>
        </el-table-column>
        <el-table-column label="VWAP" width="110">
          <template #default="{ row }">{{ formatNumber(row.vwap, 4) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Search } from '@element-plus/icons-vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { fetchEastmoneyKlines, searchSecurities } from '@/api/eastmoney'
import { useXlsxJsStyle } from '@/composables/useXlsxJsStyle'

const { loadXlsxJsStyle } = useXlsxJsStyle()

// 页面状态与价格口径配置。
const formRef = ref()
const form = reactive({ klt: '101', lmt: 2000, fqt: '1' })
const keyword = ref('')
const selectedStock = ref(null)
const securityCandidates = ref([])
let securitySearchRequestId = 0
const klineRows = ref([])
const queryData = ref(null)
const volatility = ref(null)
const priceBasis = ref('vwap')
const referenceDate = ref(getToday())
const exportFileName = ref('')
const exportDateOrder = ref('asc')
const submitting = ref(false)
const exporting = ref(false)

const volatilityPriceBases = {
  vwap: { field: 'vwap', label: 'VWAP' },
  open: { field: 'open', label: '开盘价' },
  close: { field: 'close', label: '收盘价' },
  high: { field: 'high', label: '最高价' },
  low: { field: 'low', label: '最低价' },
}

const rules = {
  lmt: [{
    validator: (rule, value, callback) => {
      const count = Number(value)
      if (!Number.isInteger(count) || count < 2 || count > 10000) {
        callback(new Error('获取条数应为 2 至 10000 的整数'))
        return
      }
      callback()
    },
    trigger: 'blur',
  }],
}

const hasAnalysis = computed(() => Boolean(queryData.value && volatility.value))
const stockCode = computed(() => (
  queryData.value ? queryData.value.secid.split('.')[1] || queryData.value.secid : ''
))
const stockName = computed(() => queryData.value?.stockName || '-')
const referenceDateText = computed(() => (
  volatility.value ? formatKlineDate(volatility.value.recent.referenceDate) : ''
))
const recentValues = computed(() => volatility.value?.recent.values || [])
const yearlyDisplayValues = computed(() => [{ result: null }].concat(volatility.value?.yearly || []))
const turnoverValues = computed(() => volatility.value?.turnover || [])
const displayRows = computed(() => getDisplayRows(klineRows.value))
const tableMeta = computed(() => (klineRows.value.length > 40
  ? '已按日期倒序展示最新20条和最早20条'
  : '已按日期倒序展示全部'))
const exportDisabled = computed(() => !klineRows.value.length || !queryData.value || !volatility.value)

// 展示和导出工具。
function formatNumber(value, digits) {
  return Number.isFinite(value) ? value.toFixed(digits) : '-'
}

function formatPercent(value) {
  return Number.isFinite(value) ? (value * 100).toFixed(2) + '%' : '不可计算'
}

function formatAmountValue(value) {
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

function roundVwap(value) {
  return Number.isFinite(value) ? Number(value.toFixed(4)) : null
}

function getVolatilityPriceBasis(value) {
  return volatilityPriceBases[value] || volatilityPriceBases.vwap
}

// 为文本单元格添加前导单引号，避免 Excel 按公式执行。
function safeExportText(value) {
  const text = String(value || '')
  return /^[=+\-@]/.test(text) ? "'" + text : text
}

function getDefaultExportFileName(query, calculation) {
  const code = query.secid.split('.')[1] || query.secid
  const oneYear = calculation?.recent.values.find((item) => item.label === '1年')
  const oneYearVolatility = oneYear?.result ? formatPercent(oneYear.result.value) : '无数据'
  return `${code}-${query.stockName || '股票'}-${oneYearVolatility}`
}

function getExportFileName(query) {
  const fileName = exportFileName.value.trim() || getDefaultExportFileName(query, volatility.value)
  return fileName.replace(/[\\/:*?"<>|]/g, '_').replace(/\.xlsx$/i, '')
}

// 导出排序始终基于副本，避免影响页面当前的日期倒序展示。
function getExportRows(rows, dateOrder) {
  const exportRows = rows.slice()
  return dateOrder === 'desc' ? exportRows.reverse() : exportRows
}

// A 股成交量以手返回，其余市场以股返回。
function getVolumeUnitByMarket(market) {
  return String(market) === '0' || String(market) === '1' ? 'hand' : 'share'
}

// 失焦时把输入文本匹配为已加载候选，与输入过程中的精确匹配共用同一份候选。
function matchCandidate(value) {
  const normalized = String(value || '').trim().toUpperCase()
  if (!normalized) {
    return null
  }
  return securityCandidates.value.find((item) => (
    item.displayName.toUpperCase() === normalized || item.code.toUpperCase() === normalized
  )) || null
}

function handleSelectStock(item) {
  selectedStock.value = item
}

function handleKeywordBlur() {
  if (!selectedStock.value) {
    selectedStock.value = matchCandidate(keyword.value)
  }
}

// 通过请求序号丢弃过期响应，避免快速输入时旧结果覆盖新结果。
function querySecurities(text, callback) {
  const trimmed = String(text || '').trim()
  if (!trimmed) {
    selectedStock.value = null
    securityCandidates.value = []
    callback([])
    return
  }
  const cached = matchCandidate(trimmed)
  if (cached) {
    selectedStock.value = cached
    callback([])
    return
  }
  selectedStock.value = null
  const requestId = ++securitySearchRequestId
  searchSecurities(trimmed).then((items) => {
    if (requestId !== securitySearchRequestId) {
      return
    }
    securityCandidates.value = items
    callback(items)
  }).catch(() => {
    if (requestId !== securitySearchRequestId) {
      return
    }
    securityCandidates.value = []
    callback([])
  })
}

// K线字段依次为日期、开高低收、成交量、成交额及三个涨跌指标。
// A 股成交量以手返回，VWAP 计算时统一换算为股。
function parseKlines(klines, volumeUnit, klt) {
  const uniqueRows = {}
  let invalidCount = 0
  let multiplier = null
  if (volumeUnit === 'hand') {
    multiplier = 100
  } else if (volumeUnit === 'share') {
    multiplier = 1
  }
  klines.forEach((line) => {
    const fields = String(line).split(',')
    const values = fields.slice(1, 11).map(Number)
    if (
      fields.length < 11 ||
      !fields[0] ||
      !getKlineDate({ stock_date: fields[0] }) ||
      values.some((value) => !Number.isFinite(value)) ||
      values[0] < 0 ||
      values[1] < 0 ||
      values[4] < 0 ||
      values[5] < 0 ||
      values[2] < Math.max(values[0], values[1]) ||
      values[3] > Math.min(values[0], values[1])
    ) {
      invalidCount++
      return
    }
    const volume = multiplier === null ? null : values[4] * multiplier
    uniqueRows[fields[0]] = {
      stock_date: fields[0],
      vwap: volume > 0 ? roundVwap(values[5] / volume) : null,
      open: values[0],
      close: values[1],
      high: values[2],
      low: values[3],
      volume_raw: values[4],
      volume_unit: volumeUnit === 'hand' ? '手' : volumeUnit === 'share' ? '股' : '不确定',
      volume,
      amount: values[5],
      amplitude: values[6],
      pct_change: values[7],
      change: values[8],
      turnover_rate: values[9],
      is_final: String(klt) === '101' && fields[0] === getToday() ? '待确认' : '是',
    }
  })
  return {
    rows: Object.keys(uniqueRows)
      .sort()
      .map((date) => uniqueRows[date]),
    invalidCount,
  }
}

function getToday() {
  const today = new Date()
  return [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, '0'),
    String(today.getDate()).padStart(2, '0'),
  ].join('-')
}

function getKlineDate(row) {
  let value = String(row.stock_date || '').replace(/\//g, '-')
  if (value.length === 10) {
    value += 'T00:00:00'
  } else {
    value = value.replace(' ', 'T')
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

// 日K线只有日期，按所选日结束时刻计算以匹配桌面端 datetime.now() 的边界。
function getVolatilityReferenceDate() {
  const parsed = getKlineDate({ stock_date: referenceDate.value })
  if (parsed) {
    parsed.setHours(23, 59, 59, 999)
  }
  return parsed
}

function formatKlineDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-')
}

// 波动率采用相邻价格简单收益率绝对值的算术平均。
function calculateAbsoluteVolatility(rows, priceField) {
  const prices = rows
    .map((row) => Number(row[priceField || 'vwap']))
    .filter((price) => Number.isFinite(price) && price > 0)
  if (prices.length < 2) {
    return null
  }
  const absoluteReturns = []
  for (let index = 1; index < prices.length; index++) {
    absoluteReturns.push(Math.abs((prices[index] - prices[index - 1]) / prices[index - 1]))
  }
  return {
    value: absoluteReturns.reduce((sum, value) => sum + value, 0) / absoluteReturns.length,
    observationCount: absoluteReturns.length,
  }
}

function filterRowsByDate(rows, startDate, endDate) {
  return rows.filter((row) => {
    const date = getKlineDate(row)
    return date && date >= startDate && date <= endDate
  })
}

function hasCompleteSpan(rows, requiredDays, toleranceDays) {
  if (rows.length < 2) {
    return false
  }
  const earliestDate = getKlineDate(rows[0])
  const latestDate = getKlineDate(rows[rows.length - 1])
  if (!earliestDate || !latestDate) {
    return false
  }
  return (latestDate.getTime() - earliestDate.getTime()) / 86400000 >= requiredDays - toleranceDays
}

function shiftDate(reference, days) {
  return new Date(reference.getTime() - days * 86400000)
}

function getKlineDataRange(rows) {
  const dates = rows
    .map(getKlineDate)
    .filter((date) => date)
    .sort((left, right) => left - right)
  if (!dates.length) {
    return '-'
  }
  return formatKlineDate(dates[0]) + ' 至 ' + formatKlineDate(dates[dates.length - 1])
}

function logVolatilityRange(type, label, rows, startDate, endDate, isComplete) {
  const firstDate = rows.length ? getKlineDate(rows[0]) : null
  const lastDate = rows.length ? getKlineDate(rows[rows.length - 1]) : null
  console.info(`[波动率计算] ${type}-${label}`, {
    请求开始日期: formatKlineDate(startDate),
    请求结束日期: formatKlineDate(endDate),
    实际最早K线日期: firstDate ? formatKlineDate(firstDate) : '-',
    实际最新K线日期: lastDate ? formatKlineDate(lastDate) : '-',
    K线记录数: rows.length,
    满足计算条件: isComplete,
  })
}

// 以指定日期为基准，计算半年至七年的近年波动率。
function calculateRecentVolatilities(rows, priceField, basisDate) {
  const effectiveDate = basisDate || getKlineDate(rows[rows.length - 1])
  const periods = [
    { label: '半年', days: 182, tolerance: 15 },
    { label: '1年', days: 365, tolerance: 30 },
    { label: '2年', days: 730, tolerance: 30 },
    { label: '3年', days: 1095, tolerance: 30 },
    { label: '4年', days: 1460, tolerance: 30 },
    { label: '5年', days: 1825, tolerance: 30 },
    { label: '6年', days: 2190, tolerance: 30 },
    { label: '7年', days: 2555, tolerance: 30 },
  ]
  const values = periods.map((period) => {
    const startDate = shiftDate(effectiveDate, period.days)
    const periodRows = filterRowsByDate(rows, startDate, effectiveDate)
    const isComplete = hasCompleteSpan(periodRows, period.days, period.tolerance)
    logVolatilityRange('近年', period.label, periodRows, startDate, effectiveDate, isComplete)
    return {
      label: period.label,
      dataRange: getKlineDataRange(periodRows),
      result: isComplete ? calculateAbsoluteVolatility(periodRows, priceField) : null,
    }
  })
  logVolatilityRange('近年', '总体', rows, getKlineDate(rows[0]), effectiveDate, rows.length >= 2)
  values.push({
    label: '总体',
    dataRange: getKlineDataRange(rows),
    result: calculateAbsoluteVolatility(rows, priceField),
  })
  return { referenceDate: effectiveDate, values }
}

// 将历史数据按连续 365 天划分年度，年度样本少于 200 条时不参与计算。
function calculateYearlyVolatilities(rows, basisDate, priceField) {
  const values = []
  let validYearRows = []
  for (let year = 1; year <= 7; year++) {
    const endDate = shiftDate(basisDate, (year - 1) * 365)
    const startDate = shiftDate(endDate, 365)
    const yearRows = filterRowsByDate(rows, startDate, endDate)
    const isComplete = yearRows.length >= 200
    logVolatilityRange('年度', `第${year}年`, yearRows, startDate, endDate, isComplete)
    const result = isComplete ? calculateAbsoluteVolatility(yearRows, priceField) : null
    if (result) {
      validYearRows = validYearRows.concat(yearRows)
    }
    values.push({
      label: `第${year}年`,
      dataRange: getKlineDataRange(yearRows),
      result,
    })
  }
  const calculatedValues = values
    .map((item) => (item.result ? item.result.value : null))
    .filter((value) => value !== null)
  values.push({
    label: '年度平均',
    detailLabel: '有效年度',
    dataRange: getKlineDataRange(validYearRows),
    result: calculatedValues.length
      ? {
        value: calculatedValues.reduce((sum, value) => sum + value, 0) / calculatedValues.length,
        observationCount: calculatedValues.length,
      }
      : null,
  })
  return values
}

// 平均成交额使用每根有效 K 线的成交额算术平均。
function calculateAverageTurnover(rows) {
  const amounts = rows
    .map((row) => Number(row.amount))
    .filter((amount) => Number.isFinite(amount) && amount >= 0)
  if (!amounts.length) {
    return null
  }
  return {
    value: amounts.reduce((sum, amount) => sum + amount, 0) / amounts.length,
    observationCount: amounts.length,
  }
}

// 平均成交额与年度波动率共用同一年度窗口和样本完整性规则。
function calculateYearlyAverageTurnovers(rows, basisDate) {
  const values = []
  for (let year = 1; year <= 7; year++) {
    const endDate = shiftDate(basisDate, (year - 1) * 365)
    const startDate = shiftDate(endDate, 365)
    const yearRows = filterRowsByDate(rows, startDate, endDate)
    values.push({
      label: `第${year}年`,
      dataRange: getKlineDataRange(yearRows),
      result: yearRows.length >= 200 ? calculateAverageTurnover(yearRows) : null,
    })
  }
  values.push({
    label: '总体',
    dataRange: getKlineDataRange(rows),
    result: calculateAverageTurnover(rows),
  })
  return values
}

// 汇总当前价格口径下的近年、年度波动率及年度平均成交额。
function calculateVolatilityAnalysis(rows, basisValue, basisDate) {
  const basis = getVolatilityPriceBasis(basisValue)
  console.info('[波动率计算] 价格口径', {
    名称: basis.label,
    字段: basis.field,
  })
  const recentVolatilities = calculateRecentVolatilities(rows, basis.field, basisDate)
  return {
    priceBasis: basisValue,
    recent: recentVolatilities,
    yearly: calculateYearlyVolatilities(rows, recentVolatilities.referenceDate, basis.field),
    turnover: calculateYearlyAverageTurnovers(rows, recentVolatilities.referenceDate),
  }
}

function volatilityCellTitle(item, unavailableText) {
  return item.result
    ? `${item.detailLabel || '有效收益率'} ${item.result.observationCount} 项`
    : unavailableText
}

function turnoverCellTitle(item) {
  return item.result
    ? `有效K线 ${item.result.observationCount} 条；数据范围：${item.dataRange}`
    : '数据不足（至少200条）'
}

// 优先使用现代剪贴板 API，非安全上下文退回到兼容方案。
function copyText(text) {
  const showResult = (success) => {
    if (success) {
      ElMessage.success('已复制到剪切板')
    } else {
      ElMessage.error('复制失败，请手动复制')
    }
  }

  const copyWithFallback = () => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      showResult(document.execCommand('copy'))
    } catch {
      showResult(false)
    }
    textarea.remove()
  }

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => showResult(true)).catch(copyWithFallback)
    return
  }
  copyWithFallback()
}

// K线较多时仅展示最新和最早各 20 条，完整数据仍保留用于计算和导出。
function getDisplayRows(rows) {
  if (rows.length <= 40) {
    return rows.slice().reverse()
  }
  return rows.slice(-20).reverse().concat(rows.slice(0, 20).reverse())
}

async function submitSearch() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!selectedStock.value) {
    ElMessage.error('请先完成股票查询')
    return
  }
  const query = {
    klt: form.klt,
    lmt: form.lmt,
    fqt: form.fqt,
    secid: selectedStock.value.secid,
    stockName: selectedStock.value.name,
    priceBasis: priceBasis.value || 'vwap',
    volumeUnit: getVolumeUnitByMarket(selectedStock.value.market),
  }
  submitting.value = true
  try {
    const response = await fetchEastmoneyKlines(query)
    if (!response?.data || !Array.isArray(response.data.klines) || !response.data.klines.length) {
      ElMessage.error(response?.msg || '东方财富未返回有效K线数据')
      return
    }
    const parsed = parseKlines(response.data.klines, query.volumeUnit, query.klt)
    if (!parsed.rows.length) {
      ElMessage.error('返回数据均未通过K线字段校验')
      return
    }
    klineRows.value = parsed.rows
    queryData.value = query
    volatility.value = calculateVolatilityAnalysis(
      parsed.rows,
      query.priceBasis,
      getVolatilityReferenceDate(),
    )
    exportFileName.value = getDefaultExportFileName(query, volatility.value)
    ElMessage.success(`已拉取 ${parsed.rows.length} 条K线数据`)
  } catch {
    ElMessage.error({
      message: 'K线接口请求失败。若浏览器拦截 JSONP，请通过后端同源代理请求东方财富接口。',
      duration: 5000,
    })
  } finally {
    submitting.value = false
  }
}

// 重算不会重新请求接口，避免切换日期或价格口径时覆盖当前快照。
function refreshVolatilityAnalysis() {
  if (!klineRows.value.length || !queryData.value) {
    return
  }
  const basisDate = getVolatilityReferenceDate()
  if (!basisDate) {
    ElMessage.error('请选择有效的计算基准日期')
    return
  }
  const oldDefaultFileName = getDefaultExportFileName(queryData.value, volatility.value)
  const currentFileName = exportFileName.value.trim()
  queryData.value.priceBasis = priceBasis.value || 'vwap'
  volatility.value = calculateVolatilityAnalysis(klineRows.value, queryData.value.priceBasis, basisDate)
  if (!currentFileName || currentFileName === oldDefaultFileName) {
    exportFileName.value = getDefaultExportFileName(queryData.value, volatility.value)
  }
}

// 以下为 xlsx-js-style 的工作簿封装：只负责单元格样式与列宽，业务数据在导出函数组装。
function getDefaultCellStyle(isHeader) {
  const style = {
    font: {
      name: 'Microsoft YaHei',
      bold: isHeader,
    },
    alignment: {
      horizontal: 'center',
      vertical: 'center',
    },
  }
  if (isHeader) {
    style.fill = {
      patternType: 'solid',
      fgColor: { rgb: 'FFF2CC' },
    }
  }
  return style
}

// 合并页面传入的样式覆盖项，只处理 Excel 样式实际使用的三层字段。
function mergeCellStyle(style, customStyle) {
  if (!customStyle) {
    return
  }
  ['font', 'fill', 'alignment'].forEach((key) => {
    if (customStyle[key]) {
      style[key] = Object.assign(style[key] || {}, customStyle[key])
    }
  })
}

function applyCellStyles(XLSX, worksheet, rows, getCellStyle) {
  rows.forEach((row, rowIndex) => {
    row.forEach((value, columnIndex) => {
      const cell = worksheet[XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex })]
      if (!cell) {
        return
      }
      const style = getDefaultCellStyle(rowIndex === 0)
      if (getCellStyle) {
        mergeCellStyle(style, getCellStyle(rowIndex, columnIndex, value, rowIndex === 0))
      }
      cell.s = style
    })
  })
}

// 未指定列宽时使用 15 个字符宽度，页面可传入 columnWidths 覆盖。
function getColumnWidths(headers, columnWidths) {
  return headers.map((header, index) => ({
    wch: columnWidths && columnWidths[index] ? columnWidths[index] : 15,
  }))
}

function ensureFileExtension(fileName) {
  return /\.xlsx$/i.test(fileName) ? fileName : fileName + '.xlsx'
}

function exportSheets(XLSX, sheets, fileName) {
  if (!Array.isArray(sheets) || sheets.length === 0) {
    throw new Error('没有可导出的工作表')
  }
  const workbook = XLSX.utils.book_new()
  sheets.forEach((sheet, index) => {
    if (!sheet || !Array.isArray(sheet.rows) || sheet.rows.length === 0) {
      throw new Error('工作表数据不能为空')
    }
    const worksheet = XLSX.utils.aoa_to_sheet(sheet.rows)
    applyCellStyles(XLSX, worksheet, sheet.rows, sheet.getCellStyle)
    worksheet['!cols'] = getColumnWidths(sheet.rows[0], sheet.columnWidths)
    XLSX.utils.book_append_sheet(workbook, worksheet, sheet.sheetName || `Sheet${index + 1}`)
  })
  XLSX.writeFile(workbook, ensureFileExtension(fileName))
}

// 导出当前快照及与页面一致的分析结果。
async function handleExport() {
  if (!klineRows.value.length || !queryData.value || !volatility.value) {
    ElMessage.error('请先拉取K线数据')
    return
  }
  const query = queryData.value
  const currentVolatility = volatility.value
  const klineExportRows = [
    [
      '证券标识',
      '证券代码',
      '证券名称',
      '日期',
      'VWAP',
      '开盘',
      '收盘',
      '最高',
      '最低',
      '原始成交量',
      '换算成交量(股)',
      '成交额',
      '振幅%',
      '涨跌幅%',
      '涨跌额',
      '换手率%',
    ],
  ]
  getExportRows(klineRows.value, exportDateOrder.value).forEach((item) => {
    klineExportRows.push([
      query.secid,
      query.secid.split('.')[1],
      safeExportText(query.stockName),
      item.stock_date,
      item.vwap,
      item.open,
      item.close,
      item.high,
      item.low,
      item.volume_raw,
      item.volume,
      item.amount,
      item.amplitude,
      item.pct_change,
      item.change,
      item.turnover_rate,
    ])
  })
  const analysisRows = [
    [
      '数据源',
      '东方财富',
      '证券标识',
      query.secid,
      '证券名称',
      safeExportText(query.stockName),
      'K线周期',
      query.klt,
      '复权方式',
      query.fqt,
    ],
    [
      '取数时间',
      new Date().toISOString(),
      '成交量单位',
      klineRows.value[0].volume_unit,
      '波动率价格',
      getVolatilityPriceBasis(currentVolatility.priceBasis).label,
      '算法版本',
      'mean_abs_simple_return',
    ],
    [],
    ['波动率参考日期', formatKlineDate(currentVolatility.recent.referenceDate)],
    ['近年波动率'],
    ['区间', '波动率', '有效收益率数', '数据范围'],
  ]
  currentVolatility.recent.values.forEach((item) => {
    analysisRows.push([
      item.label,
      item.result ? formatPercent(item.result.value) : '-',
      item.result ? item.result.observationCount : 0,
      item.dataRange,
    ])
  })
  analysisRows.push(['年度波动率'])
  analysisRows.push(['区间', '波动率', '有效收益率数', '数据范围'])
  currentVolatility.yearly.forEach((item) => {
    analysisRows.push([
      item.label,
      item.result ? formatPercent(item.result.value) : '-',
      item.result ? item.result.observationCount : 0,
      item.dataRange,
    ])
  })
  exporting.value = true
  try {
    const XLSX = await loadXlsxJsStyle()
    exportSheets(
      XLSX,
      [
        {
          rows: klineExportRows,
          sheetName: 'K线数据',
          columnWidths: [
            16, 14, 18, 20, 15, 15, 15, 15,
            18, 18, 20, 15, 12, 12, 15, 14,
          ],
        },
        {
          rows: analysisRows,
          sheetName: '分析说明',
          columnWidths: [16, 18, 16, 18, 16, 18, 16, 18, 16, 18],
          getCellStyle: (rowIndex) => {
            if (rowIndex === 4 || rowIndex === 5 || rowIndex === 15 || rowIndex === 16) {
              return {
                font: { bold: true },
                fill: { patternType: 'solid', fgColor: { rgb: 'FFF2CC' } },
              }
            }
          },
        },
      ],
      getExportFileName(query),
    )
  } catch (error) {
    ElMessage.error(error?.message || 'Excel导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.kline-card {
  padding: 20px;
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: linear-gradient(180deg, var(--app-surface-elevated) 0%, var(--app-surface) 100%);
}

/* 查询表单：4 个字段与提交按钮同行排布 */
.kline-search-form {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
  align-items: end;
  gap: 4px 24px;
}

.kline-search-form .el-form-item {
  min-width: 0;
  margin-bottom: 0;
}

.kline-search-form .el-select,
.kline-search-form .el-input-number,
.stock-autocomplete {
  width: 100%;
}

.kline-submit {
  justify-self: end;
}

/* 波动率分析区 */
.analysis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.analysis-title {
  color: var(--app-text);
  font-size: 18px;
  font-weight: 800;
}

.analysis-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.analysis-basis {
  display: flex;
  align-items: center;
  gap: 8px;
}

.analysis-label {
  color: var(--app-text-muted);
  font-size: 13px;
  white-space: nowrap;
}

.price-basis-select {
  width: 140px;
}

.reference-date-picker {
  width: 150px;
}

.analysis-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-bottom: 10px;
  color: var(--app-text-muted);
  font-size: 13px;
}

.analysis-copy-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 10px;
  color: var(--app-text);
  background: var(--app-surface-elevated);
  border: 1px solid var(--app-border);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.analysis-copy-block span {
  color: var(--app-text-muted);
}

.analysis-copy-block strong {
  color: var(--app-primary);
  font-weight: 600;
}

.analysis-copy-block:hover,
.analysis-copy-block:focus {
  border-color: var(--app-primary);
  outline: 0;
}

.analysis-reference {
  padding: 0;
  color: var(--app-primary);
  background: none;
  border: 0;
  font-size: 13px;
  cursor: pointer;
}

.analysis-reference:hover,
.analysis-reference:focus {
  text-decoration: underline;
  outline: 0;
}

.volatility-comparison-wrap {
  overflow-x: auto;
}

.volatility-comparison {
  width: 100%;
  min-width: 900px;
  margin: 0;
  border-collapse: collapse;
}

.volatility-comparison th,
.volatility-comparison td {
  min-width: 72px;
  padding: 8px 10px;
  color: var(--app-text-muted);
  font-size: 13px;
  text-align: center;
  white-space: nowrap;
  border: 1px solid var(--app-border);
}

.volatility-comparison th:first-child,
.volatility-comparison td:first-child {
  min-width: 80px;
  color: var(--app-text);
  text-align: left;
}

.volatility-comparison td strong {
  color: var(--app-text);
  font-size: 14px;
}

.volatility-row-label {
  color: var(--app-primary) !important;
  font-weight: 700;
}

.average-turnover-analysis {
  margin-top: 1.5rem;
}

.average-turnover-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 700;
}

.average-turnover-header small {
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 400;
}

/* 数据表格区 */
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

.table-title {
  color: var(--app-text);
  font-size: 22px;
  font-weight: 800;
}

.table-meta {
  margin-left: 12px;
  color: var(--app-text-muted);
  font-size: 13px;
  font-weight: 400;
}

.table-operate {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.export-file-name {
  width: 260px;
}

.export-date-order {
  display: flex;
  align-items: center;
  gap: 6px;
}

.export-order-select {
  width: 130px;
}

/* 窄宽度布局 */
@media (max-width: 1100px) {
  .kline-search-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kline-search-form .el-form-item:first-child {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .kline-search-form {
    grid-template-columns: 1fr;
  }

  .kline-submit {
    justify-self: start;
  }

  .analysis-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .analysis-controls {
    flex-wrap: wrap;
  }

  .export-file-name {
    width: 100%;
  }
}
</style>
