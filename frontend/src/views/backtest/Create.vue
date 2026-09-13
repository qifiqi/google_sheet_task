<template>
  <div class="app-page backtest-create-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Builder</div>
        <h2 class="page-title">创建回测训练任务</h2>
        <p class="page-description">识别 Google Sheet、选择股票、导入参数并创建任务。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.push('/backtest/list')">返回列表</el-button>
      </div>
    </div>

    <el-card shadow="never" class="page-section">
      <el-row :gutter="16" align="middle">
        <el-col :xs="24" :lg="10">
          <el-form-item label="Google Sheet 链接">
            <div ref="sheetSelectorShellRef" class="backtest-create-page__search-wrap">
              <el-input
                v-model="sheetUrl"
                placeholder="输入 Google Sheet 链接或 Sheet ID"
                @focus="loadPresetSheets"
                @click="loadPresetSheets"
                @input="onSheetUrlInput"
                @keyup.enter="analyze"
              />
              <div v-if="presetSheetPanelOpen" class="backtest-create-page__search-panel">
                <div v-if="presetSheetsLoading" class="panel-note backtest-create-page__panel-note">加载中...</div>
                <div v-else-if="!presetSheets.length" class="panel-note backtest-create-page__panel-note">
                  暂无可用预设 Sheet
                </div>
                <div
                  v-for="sheet in presetSheets"
                  :key="sheet.id"
                  class="backtest-create-page__search-item"
                  @mousedown.prevent="selectPresetSheet(sheet)"
                >
                  <div class="backtest-create-page__search-code">
                    {{ sheet.name || '未命名 Sheet' }}
                    <span class="panel-note">ID: {{ sheet.spreadsheet_id || '-' }}</span>
                  </div>
                  <div v-if="sheet.remark" class="panel-note">{{ sheet.remark }}</div>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-col>

        <el-col :xs="24" :lg="6">
          <el-form-item label="股票代码">
            <div ref="stockSearchShellRef" class="backtest-create-page__search-wrap">
              <el-input
                v-model="stockCode"
                placeholder="如 AAPL、MSFT、平安银行"
                @input="onStockInput"
                @keyup.enter="searchStockSuggestionsNow"
              />
              <div v-if="stockSearchPanelOpen" class="backtest-create-page__search-panel">
                <div v-if="!stockSearchResults.length" class="panel-note backtest-create-page__panel-note">
                  {{ stockCode.trim() ? `未找到 “${stockCode.trim()}” 的匹配结果` : '请输入股票代码' }}
                </div>
                <div
                  v-for="stock in stockSearchResults"
                  :key="stock.code"
                  class="backtest-create-page__search-item"
                  @mousedown.prevent="selectStock(stock)"
                >
                  <div class="backtest-create-page__search-code">{{ stock.code }}</div>
                  <div class="panel-note">{{ stock.label || stock.name || '' }}</div>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-col>

        <el-col :xs="24" :lg="4">
          <el-form-item label="市场类型">
            <el-select v-model="form.market_type" class="full-width" @change="onMarketTypeChange">
              <el-option
                v-for="market in stockMarkets"
                :key="market.value"
                :value="market.value"
                :label="market.label"
              />
            </el-select>
          </el-form-item>
        </el-col>

        <el-col :xs="24" :lg="4">
          <el-form-item label="&nbsp;">
            <el-button type="primary" class="full-width" :loading="analyzing" @click="analyze">识别链接</el-button>
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <div>
          <h3 class="section-title section-title--muted">任务配置</h3>
          <div class="panel-note">基础信息与年份范围</div>
        </div>
      </div>

      <div v-if="sheetInfoVisible" class="info-banner backtest-create-page__sheet-banner">
        <span>
          <el-tag type="primary">{{ modelVersionLabel }}</el-tag>
          <strong>{{ sheetTitle || '-' }}</strong>
          <span class="panel-note">Sheet: {{ worksheetsText }}</span>
        </span>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :sm="8" :lg="6">
          <el-form-item label="任务名称">
            <el-input v-model="form.task_name" placeholder="自动生成，例如 C3-NVDA" @input="onTaskNameInput" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8" :lg="6">
          <el-form-item label="回测 Token">
            <el-select v-model="form.token_id" class="full-width" placeholder="暂无可用 Token">
              <el-option
                v-for="token in tokens"
                :key="token.id"
                :value="String(token.id)"
                :label="tokenLabel(token)"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="isC3Model" :xs="24" :sm="8" :lg="4">
          <el-form-item label="手续费">
            <el-input v-model="form.commission" placeholder="如 0.0350%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="4">
          <el-form-item label="K线复权">
            <el-select v-model="form.kline_adjustment" class="full-width">
              <el-option value="forward" label="前复权" />
              <el-option value="back" label="后复权" />
              <el-option value="none" label="不复权" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="4">
          <el-form-item label="价格模式">
            <el-select v-model="form.price_mode" class="full-width" :disabled="isC7V03Model">
              <el-option value="vwap_price" label="加权平均价" />
              <el-option value="kp_price" label="开盘价" />
              <el-option value="sp_price" label="收盘价" />
              <el-option value="ohlc_price" label="OHLC（开高低收）" :disabled="!isC7V03Model" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="4">
          <el-form-item label="K线数据源">
            <el-select v-model="form.kline_data_source" class="full-width">
              <el-option value="akshare" label="AKShare（默认）" />
              <el-option value="dfcf" label="东方财富" />
              <el-option value="qq" label="腾讯" />
              <el-option value="yahoo" label="Yahoo" />
              <el-option value="tdx" label="通达信（仅A股）" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="4">
          <el-form-item label="K 线截至日期">
            <el-date-picker
              v-model="form.end_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="留空使用运行日前一天"
              class="full-width"
              clearable
            />
            <div class="panel-note">留空时使用运行日前一天；近 N 年会按该日期向前计算。</div>
          </el-form-item>
        </el-col>
      </el-row>

      <div class="sub-card backtest-create-page__year-card">
        <div class="section-heading backtest-create-page__year-head">
          <div>
            <div class="backtest-create-page__card-title">年份范围</div>
            <div class="panel-note">可同时选择近年范围和整年范围，系统会带入任务配置。</div>
          </div>
          <div class="control-row">
            <el-checkbox v-model="useRecentYears" label="近 N 年" @change="onRecentYearsToggle" />
            <el-checkbox v-model="useFullYears" label="完整年份" @change="onFullYearsToggle" />
          </div>
        </div>

        <el-row :gutter="16">
          <el-col v-if="useRecentYears" :xs="24" :sm="12">
            <div class="backtest-create-page__option-title">近 N 年</div>
            <div class="tag-wall">
              <el-checkbox-group v-model="selectedRecentYears">
                <el-checkbox v-for="year in recentYearOptions" :key="year" :value="year" :label="year">
                  近 {{ year }} 年
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </el-col>

          <el-col v-if="useFullYears" :xs="24" :sm="12">
            <div class="backtest-create-page__option-title">完整年份</div>
            <div class="tag-wall">
              <el-checkbox-group v-model="selectedFullYears">
                <el-checkbox v-for="year in fullYearOptions" :key="year" :value="year" :label="year">
                  {{ year }}
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </el-col>
        </el-row>

        <div class="panel-note backtest-create-page__years-display">
          近 N 年：{{ recentYearsText }}；完整年份：{{ fullYearsText }}
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <div>
          <h3 class="section-title section-title--muted">参数配置</h3>
          <div class="panel-note">支持手动录入、粘贴追加或从 Excel 导入。</div>
        </div>
        <div class="section-actions backtest-create-page__param-actions">
          <el-upload :show-file-list="false" accept=".xlsx,.xlsm" :before-upload="importExcelFile">
            <el-button size="small" :loading="importingExcel">导入 Excel</el-button>
          </el-upload>
          <el-popover placement="top" trigger="focus" width="420" title="粘贴与复制说明">
            <template #reference>
              <el-button size="small">?</el-button>
            </template>
            <div class="backtest-create-page__help">
              <p><strong>C3 粘贴</strong>：每行 6 个业务参数时顺序为 xm、单边保护 1、中立限仓、指数跟踪、一窝蜂 S、一窝蜂 B，系统自动计算 单边保护 2 = 2 - 单边保护 1；每行 7 个业务参数时按完整字段处理。</p>
              <p><strong>C3 复制</strong>：复制当前表格为 Tab 分隔行，包含 Commission 和后续参数列，可直接贴到其他任务或 Excel。</p>
              <p><strong>C5 粘贴/复制</strong>：每行 2 列，顺序为 X Multiplier、ML。</p>
              <p><strong>C7 粘贴/复制</strong>：每行 2 列，顺序为 X Multiplier、ML。</p>
            </div>
          </el-popover>
          <el-button size="small" @click="pasteParametersFromClipboard">粘贴追加</el-button>
          <el-button size="small" @click="copyParametersToClipboard">复制参数</el-button>
          <el-button size="small" type="primary" plain @click="addParameterRow">添加参数</el-button>
          <el-button size="small" type="primary" :loading="submitting" @click="submit">创建任务</el-button>
        </div>
      </div>

      <div :class="['panel-note', statusToneClass]">{{ excelImportStatus }}</div>

      <div v-if="!paramRows.length" class="panel-note panel-note--center backtest-create-page__empty">
        先识别模型或直接添加参数行。
      </div>

      <el-table v-else :data="paramRows" border>
        <el-table-column
          v-for="field in currentFields"
          :key="field.key"
          :label="field.label"
          min-width="120"
        >
          <template #default="{ row }">
            <el-input v-model="row[field.key]" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="paramRows.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { importExcel, searchStocks } from '@/api/backtest'
import { getWorksheets, getGoogleSheets, getTokens } from '@/api/googleSheet'
import { getEnums } from '@/api/meta'
import { createTask } from '@/api/task'
import { previousWeekday, formatDate } from '@/utils/tradingDate'

const router = useRouter()

const DEFAULT_C3_COMMISSION = '0.0350%'
const STOCK_SEARCH_DEBOUNCE_MS = 1000
const PRESET_SHEETS_CACHE_KEY = 'backtest_training_google_sheets_v2'
const PRESET_SHEETS_CACHE_TTL = 5 * 60 * 1000

// 参数字段与静态版 create 页 FIELD_MAP 逐字段一致（业务参数列，不含佣金）。
const FIELD_MAP = {
  c7: [
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'ml', label: 'ML (ml)' }
  ],
  c5: [
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'ml', label: 'ML (ml)' }
  ],
  c3: [
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'dbbh1', label: '单边保护 1' },
    { key: 'dbbh2', label: '单边保护 2' },
    { key: 'zlxc', label: '中立限仓' },
    { key: 'zsgz', label: '指数跟踪' },
    { key: 'ywf1', label: '一窝蜂 S' },
    { key: 'ywf2', label: '一窝蜂 B' }
  ]
}

const currentYear = new Date().getFullYear()

// ---------- 状态 ----------
const sheetUrl = ref('')
const analyzing = ref(false)
const submitting = ref(false)
const importingExcel = ref(false)

const spreadsheetId = ref('')
const sheetTitle = ref('')
const selectedWorksheetName = ref('')
const worksheetsList = ref([])
const currentModelVersion = ref('c3')
const currentC7ModelVersion = ref('c7_0_2')
const selectedGoogleSheetId = ref(null)
const currentExcelImport = ref(null)

const stockCode = ref('')
const selectedStockSuggestion = ref(null)
const stockSearchResults = ref([])
const stockSearchPanelOpen = ref(false)
let stockSearchTimer = null

const stockMarkets = ref([])
const tokens = ref([])

const presetSheets = ref([])
const presetSheetsLoading = ref(false)
const presetSheetPanelOpen = ref(false)
let presetSheetsLoaded = false

const sheetSelectorShellRef = ref(null)
const stockSearchShellRef = ref(null)

const form = reactive({
  task_name: '',
  token_id: '',
  commission: DEFAULT_C3_COMMISSION,
  market_type: 'cn',
  kline_adjustment: 'forward',
  price_mode: 'sp_price',
  kline_data_source: 'akshare',
  end_date: formatDate(previousWeekday())
})
let lastEditablePriceMode = 'sp_price'
let taskNameTouched = false

const useRecentYears = ref(false)
const useFullYears = ref(false)
const recentYearOptions = ref([1, 2, 3, 5, 7])
const fullYearOptions = ref(Array.from({ length: 7 }, (_, index) => currentYear - index))
const selectedRecentYears = ref([1, 2, 3])
const selectedFullYears = ref(fullYearOptions.value.slice(0, 3))

const paramRows = ref([])
const excelImportStatus = ref('')
const statusTone = ref('muted')

// ---------- 计算属性 ----------
const resolvedModelVersion = computed(() => ['c5', 'c7'].includes(currentModelVersion.value) ? currentModelVersion.value : 'c3')
const isC3Model = computed(() => resolvedModelVersion.value === 'c3')
const isC7V03Model = computed(() => resolvedModelVersion.value === 'c7' && currentC7ModelVersion.value === 'c7_0_3')
const currentFields = computed(() => FIELD_MAP[resolvedModelVersion.value] || FIELD_MAP.c3)
const modelVersionLabel = computed(() => resolvedModelVersion.value.toUpperCase())
const sheetInfoVisible = computed(() => Boolean(sheetTitle.value || selectedWorksheetName.value))
const worksheetsText = computed(() => {
  if (selectedWorksheetName.value) return selectedWorksheetName.value
  return worksheetsList.value.length ? worksheetsList.value.join(' / ') : '-'
})
const recentYearsText = computed(() => {
  const years = useRecentYears.value ? getCheckedRecentYears() : []
  return years.length ? years.join('、') : '未选择'
})
const fullYearsText = computed(() => {
  const years = useFullYears.value ? getCheckedFullYears() : []
  return years.length ? years.join('、') : '未选择'
})
const statusToneClass = computed(() => (
  statusTone.value === 'success' ? 'backtest-create-page__status-success'
    : statusTone.value === 'danger' ? 'backtest-create-page__status-danger'
      : ''
))

// ---------- 工具 ----------
function setExcelImportStatus(message, tone = 'muted') {
  excelImportStatus.value = message || ''
  statusTone.value = tone
}

function normalizeMarketTypeValue(value) {
  const market = String(value || '').trim().toLowerCase()
  return stockMarkets.value.some((item) => item.value === market)
    ? market
    : (stockMarkets.value[0]?.value || 'cn')
}

function syncCommissionWithMarketType(value) {
  const market = stockMarkets.value.find((item) => item.value === normalizeMarketTypeValue(value))
  form.commission = market?.default_commission || ''
}

function extractSpreadsheetId(value) {
  const rawValue = String(value || '').trim()
  const urlMatch = rawValue.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  if (urlMatch) {
    return urlMatch[1]
  }
  return /^[a-zA-Z0-9-_]+$/.test(rawValue) ? rawValue : ''
}

function buildGoogleSheetUrl(id) {
  return `https://docs.google.com/spreadsheets/d/${encodeURIComponent(id)}/edit`
}

function sanitizeTaskTitlePart(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

function buildDefaultTaskName() {
  const fallbackCode = stockCode.value.trim()
    ? sanitizeTaskTitlePart(stockCode.value.trim().toUpperCase())
    : ''
  const stockPart = selectedStockSuggestion.value && normalizeMarketTypeValue(form.market_type) === 'cn'
    ? sanitizeTaskTitlePart(selectedStockSuggestion.value.name) || fallbackCode
    : fallbackCode
  const modelVersion = resolvedModelVersion.value.toUpperCase()
  return stockPart ? `${modelVersion}-${stockPart}` : ''
}

function syncTaskNameInput(force = false) {
  const nextName = buildDefaultTaskName()
  if (!nextName) {
    return
  }
  if (force || !taskNameTouched || !form.task_name.trim()) {
    form.task_name = nextName
    taskNameTouched = false
  }
}

function onTaskNameInput() {
  taskNameTouched = Boolean(form.task_name.trim())
}

function inferModelVersion(title) {
  const normalized = String(title || '').toUpperCase()
  if (normalized.includes('C7')) {
    return 'c7'
  }
  return normalized.includes('C5') || normalized.includes('C4') ? 'c5' : 'c3'
}

function inferC7ModelVersion(value) {
  const normalized = String(value || '').toUpperCase()
  return normalized.includes('C7.0.3') || normalized.includes('C7_0_3')
    ? 'c7_0_3'
    : 'c7_0_2'
}

function getCheckedRecentYears() {
  return [...selectedRecentYears.value]
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b)
}

function getCheckedFullYears() {
  return [...selectedFullYears.value]
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b)
}

function ensureDefaultRecentYearsSelection() {
  if (selectedRecentYears.value.length) {
    return
  }
  selectedRecentYears.value = [1, 2, 3]
}

function ensureDefaultFullYearsSelection() {
  if (selectedFullYears.value.length) {
    return
  }
  selectedFullYears.value = fullYearOptions.value.slice(0, 3)
}

function onRecentYearsToggle(checked) {
  if (checked) {
    ensureDefaultRecentYearsSelection()
  }
}

function onFullYearsToggle(checked) {
  if (checked) {
    ensureDefaultFullYearsSelection()
  }
}

// ---------- 价格模式（C7.0.3 强制 OHLC 并锁定） ----------
function syncPriceModeForModel() {
  if (isC7V03Model.value) {
    if (form.price_mode !== 'ohlc_price') {
      lastEditablePriceMode = form.price_mode
    }
    form.price_mode = 'ohlc_price'
    return
  }
  if (form.price_mode === 'ohlc_price') {
    form.price_mode = lastEditablePriceMode
  }
}

// ---------- 参数表 ----------
function createEmptyRow() {
  const row = {}
  currentFields.value.forEach((field) => {
    row[field.key] = ''
  })
  return row
}

function addParameterRow(initialValues = null) {
  const row = createEmptyRow()
  if (initialValues) {
    currentFields.value.forEach((field) => {
      row[field.key] = initialValues[field.key] ?? ''
    })
  }
  paramRows.value.push(row)
}

function resetParameterTable(rows = []) {
  paramRows.value = []
  const projected = projectImportedRows(rows)
  if (projected.length) {
    projected.forEach((row) => addParameterRow(row))
  } else {
    addParameterRow()
  }
}

function projectImportedRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => {
      const projected = {}
      currentFields.value.forEach((field) => {
        projected[field.key] = row?.[field.key] ? String(row[field.key]).trim() : ''
      })
      return projected
    })
    .filter((row) => Object.values(row).some(Boolean))
}

function collectParameterDraftRows() {
  return paramRows.value.map((row) => (
    currentFields.value.map((field) => String(row[field.key] ?? '').trim())
  ))
}

function getCommissionValue() {
  const value = form.commission.trim()
  return value || DEFAULT_C3_COMMISSION
}

function collectParameters() {
  const rows = collectParameterDraftRows().filter((row) => row.some(Boolean))
  if (resolvedModelVersion.value === 'c3') {
    const commission = getCommissionValue()
    return rows.map((row) => [commission, ...row])
  }
  return rows
}

// ---------- 粘贴 / 复制 ----------
function splitPastedParameterLine(line) {
  const value = String(line || '').trim()
  if (!value) {
    return []
  }
  if (value.includes('\t')) {
    return value.split('\t')
  }
  if (value.includes(',')) {
    return value.split(',')
  }
  if (value.includes('，')) {
    return value.split('，')
  }
  return value.split(/\s+/)
}

function normalizePastedCell(value) {
  return String(value ?? '')
    .replace(/\r/g, '')
    .trim()
}

function normalizeHeaderToken(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s_()（）:：/-]+/g, '')
}

function isCommissionCell(value) {
  const normalized = normalizePastedCell(value).toLowerCase()
  if (!normalized) {
    return false
  }
  return normalized.includes('%') || normalized === 'commission' || normalized === '手续费'
}

function isPastedHeaderRow(cells) {
  const headerTokens = new Set([
    'commission',
    '手续费',
    'xm',
    'xmultiplier',
    'ml',
    'dbbh1',
    'dbbh2',
    'zlxc',
    'zsgz',
    'ywf1',
    'ywf2',
    '单边保护1',
    '单边保护2',
    '中立限仓',
    '指数跟踪'
  ])
  return cells.some((cell) => headerTokens.has(normalizeHeaderToken(cell)))
}

function formatDerivedProtectionValue(value) {
  if (!Number.isFinite(value)) {
    return ''
  }
  const fixed = value.toFixed(12).replace(/0+$/, '').replace(/\.$/, '')
  return fixed === '-0' ? '0' : fixed
}

function deriveSingleSideProtection2(value) {
  const normalized = normalizePastedCell(value).replace(/,/g, '')
  if (!normalized) {
    return ''
  }
  const numericValue = Number(normalized)
  if (!Number.isFinite(numericValue)) {
    return ''
  }
  return formatDerivedProtectionValue(2 - numericValue)
}

function normalizeC3BusinessCells(cells) {
  const sourceCells = cells.slice()
  if (sourceCells.length === 6) {
    return [
      sourceCells[0],
      sourceCells[1],
      deriveSingleSideProtection2(sourceCells[1]),
      sourceCells[2],
      sourceCells[3],
      sourceCells[4],
      sourceCells[5]
    ]
  }
  return sourceCells
}

function parsePastedParameterRows(rawText) {
  const rows = String(rawText || '')
    .split(/\n+/)
    .map((line) => splitPastedParameterLine(line).map(normalizePastedCell))
    .filter((cells) => cells.some((cell) => cell !== ''))

  if (!rows.length) {
    return []
  }

  const dataRows = isPastedHeaderRow(rows[0]) ? rows.slice(1) : rows
  const c3Mode = resolvedModelVersion.value === 'c3'
  const expectedColumnCount = currentFields.value.length
  const firstDataRow = dataRows[0] || []
  const hasLeadingCommission = c3Mode
    && firstDataRow.length > expectedColumnCount - 1
    && (isCommissionCell(firstDataRow[0]) || firstDataRow.length === expectedColumnCount + 1)

  if (hasLeadingCommission && firstDataRow[0]) {
    form.commission = firstDataRow[0]
  }

  return dataRows
    .map((cells) => {
      const sourceCells = c3Mode
        ? normalizeC3BusinessCells(hasLeadingCommission ? cells.slice(1) : cells)
        : (hasLeadingCommission ? cells.slice(1) : cells)
      const projected = {}
      currentFields.value.forEach((field, index) => {
        projected[field.key] = sourceCells[index] || ''
      })
      return projected
    })
    .filter((row) => Object.values(row).some(Boolean))
}

async function requestManualClipboardText(message) {
  try {
    const { value } = await ElMessageBox.prompt(`${message} 请在下方粘贴参数内容：`, '粘贴参数', {
      inputType: 'textarea',
      inputPlaceholder: '在这里粘贴从 Excel 或其他任务复制的参数',
      confirmButtonText: '追加参数',
      cancelButtonText: '取消',
    })
    return value || ''
  } catch {
    return ''
  }
}

async function readClipboardText() {
  const canUseClipboardApi = window.isSecureContext && navigator.clipboard?.readText
  if (!canUseClipboardApi) {
    return requestManualClipboardText('当前页面不是 HTTPS，浏览器无法授予剪切板读取权限。')
  }

  try {
    if (navigator.permissions?.query) {
      const status = await navigator.permissions.query({ name: 'clipboard-read' })
      if (status.state === 'denied') {
        return requestManualClipboardText('浏览器已拒绝剪切板读取权限。')
      }
    }
    return await navigator.clipboard.readText()
  } catch {
    return requestManualClipboardText('未完成剪切板权限授权，或浏览器暂时无法读取剪切板。')
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
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  textarea.remove()
  if (!ok) {
    throw new Error('复制失败，请检查浏览器剪切板权限')
  }
}

function parameterRowsToClipboard() {
  return collectParameters()
    .filter((row) => Array.isArray(row) && row.some((value) => String(value ?? '').trim()))
    .map((row) => row.join('\t'))
    .join('\n')
}

function clearPlaceholderRowsBeforeAppend() {
  const hasValues = collectParameterDraftRows().some((row) => row.some(Boolean))
  if (!hasValues) {
    paramRows.value = []
  }
}

async function pasteParametersFromClipboard() {
  try {
    const raw = await readClipboardText()
    const rows = parsePastedParameterRows(raw)
    if (!rows.length) {
      setExcelImportStatus('剪切板中没有解析到有效参数', 'danger')
      return
    }
    clearPlaceholderRowsBeforeAppend()
    rows.forEach((row) => addParameterRow(row))
    setExcelImportStatus(`已追加 ${rows.length} 行参数`, 'success')
  } catch (error) {
    ElMessage.error(error.message || '读取剪切板失败')
  }
}

async function copyParametersToClipboard() {
  try {
    const text = parameterRowsToClipboard()
    if (!text) {
      throw new Error('当前没有可复制的参数')
    }
    await writeClipboardText(text)
    setExcelImportStatus('参数已复制，可直接粘贴到其他单产品回测或 Excel', 'success')
  } catch (error) {
    ElMessage.error(error.message || '复制失败')
  }
}

// ---------- 预设 Sheet ----------
function getCachedPresetSheets() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(PRESET_SHEETS_CACHE_KEY) || 'null')
    if (cached && cached.expires_at > Date.now() && Array.isArray(cached.items)) {
      return cached.items
    }
  } catch {
    sessionStorage.removeItem(PRESET_SHEETS_CACHE_KEY)
  }
  return null
}

function cachePresetSheets(items) {
  try {
    sessionStorage.setItem(PRESET_SHEETS_CACHE_KEY, JSON.stringify({
      expires_at: Date.now() + PRESET_SHEETS_CACHE_TTL,
      items,
    }))
  } catch {
    // sessionStorage 写入失败（隐私模式等）时静默降级为不缓存
  }
}

async function loadPresetSheets() {
  presetSheetPanelOpen.value = true
  const cachedItems = getCachedPresetSheets()
  if (cachedItems) {
    presetSheets.value = cachedItems
    presetSheetsLoaded = true
    return
  }
  if (presetSheetsLoading.value) {
    return
  }

  presetSheetsLoading.value = true
  try {
    const data = await getGoogleSheets({ table_type: 'backtest_training' })
    presetSheets.value = Array.isArray(data?.items) ? data.items : []
    cachePresetSheets(presetSheets.value)
    presetSheetsLoaded = true
  } catch {
    presetSheets.value = []
    ElMessage.error('加载单品回测 Sheet 失败')
  } finally {
    presetSheetsLoading.value = false
  }
}

async function selectPresetSheet(sheet) {
  selectedGoogleSheetId.value = Number(sheet.id)
  sheetUrl.value = buildGoogleSheetUrl(sheet.spreadsheet_id)
  presetSheetPanelOpen.value = false
  await analyze()
}

function onSheetUrlInput() {
  selectedGoogleSheetId.value = null
  clearSelectedSheetInfo()
}

// ---------- 识别 ----------
function clearSelectedSheetInfo() {
  spreadsheetId.value = ''
  sheetTitle.value = ''
  selectedWorksheetName.value = ''
  worksheetsList.value = []
  currentModelVersion.value = 'c3'
  currentC7ModelVersion.value = 'c7_0_2'
  currentExcelImport.value = null
  syncPriceModeForModel()
}

function renderSheetInfo(title, worksheets) {
  currentModelVersion.value = inferModelVersion(title)
  currentC7ModelVersion.value = inferC7ModelVersion(title)
  sheetTitle.value = title || ''
  worksheetsList.value = Array.isArray(worksheets) ? worksheets.map(String) : []
  selectedWorksheetName.value = worksheetsList.value.length
    ? String(worksheetsList.value[0]).trim()
    : ''
  currentExcelImport.value = null
  syncPriceModeForModel()
  setExcelImportStatus('')
  syncTaskNameInput(true)
  resetParameterTable()
}

async function analyze() {
  const id = extractSpreadsheetId(sheetUrl.value)
  if (!id) {
    clearSelectedSheetInfo()
    ElMessage.error('请输入有效的 Google Sheet 链接或 Sheet ID')
    return
  }

  analyzing.value = true
  try {
    const data = await getWorksheets({ spreadsheet_id: id })
    spreadsheetId.value = id
    renderSheetInfo(data.title || '', data.worksheets || [])
  } catch (error) {
    clearSelectedSheetInfo()
    ElMessage.error(error.message || '识别链接失败')
  } finally {
    analyzing.value = false
  }
}

// ---------- Excel 导入 ----------
async function importExcelFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  importingExcel.value = true
  try {
    const data = await importExcel(formData)

    currentModelVersion.value = inferModelVersion(data.model_version || 'c3')
    currentC7ModelVersion.value = inferC7ModelVersion(data.model_version || sheetTitle.value)
    const importedRows = Array.isArray(data.parameters) ? data.parameters : []
    currentExcelImport.value = data.excel_import || null
    if (data.stock_code) {
      stockCode.value = String(data.stock_code).trim().toUpperCase()
    }
    if (Array.isArray(data.recent_years)) {
      selectedRecentYears.value = data.recent_years.filter((value) => recentYearOptions.value.includes(Number(value)))
      useRecentYears.value = data.recent_years.length > 0
    }
    if (Array.isArray(data.full_years)) {
      selectedFullYears.value = data.full_years.filter((value) => fullYearOptions.value.includes(Number(value)))
      useFullYears.value = data.full_years.length > 0
    }
    if (data.end_date) {
      form.end_date = String(data.end_date)
    }

    syncPriceModeForModel()
    if (data.sheet_name) {
      selectedWorksheetName.value = String(data.sheet_name).trim()
    }
    if (!sheetTitle.value && data.sheet_name) {
      sheetTitle.value = String(data.sheet_name).trim()
    }
    syncTaskNameInput(true)
    resetParameterTable(importedRows)
    setExcelImportStatus(`已导入 ${importedRows.length} 组参数`, 'success')
  } catch (error) {
    setExcelImportStatus(error.message || 'Excel 导入失败', 'danger')
  } finally {
    importingExcel.value = false
  }
  return false
}

// ---------- 市场枚举 / Token ----------
async function loadStockMarkets() {
  try {
    const payload = await getEnums()
    stockMarkets.value = payload?.stock_markets || []
    form.market_type = normalizeMarketTypeValue('cn')
    syncCommissionWithMarketType(form.market_type)
  } catch {
    stockMarkets.value = []
    ElMessage.error('市场枚举加载失败')
  }
}

function onMarketTypeChange(value) {
  if (selectedStockSuggestion.value && value !== selectedStockSuggestion.value.market_type) {
    selectedStockSuggestion.value = null
  }
  syncCommissionWithMarketType(value)
}

function tokenLabel(token) {
  const maxUsage = Number(token.max_usage_count || 0) > 0 ? token.max_usage_count : '无限'
  return `${token.name} | 占用 ${token.current_in_use_count || 0} | 累计 ${token.task_usage_count || 0} | 上限 ${maxUsage}`
}

async function loadTokens() {
  try {
    const data = await getTokens({ task_type: 'backtest_training' })
    const allTokens = Array.isArray(data.tokens) ? data.tokens : []
    // 只展示回测可用的 Token：启用且未达到最大占用。
    tokens.value = allTokens.filter((token) => token.is_active && token.is_available)
    const firstAvailable = tokens.value[0]
    if (firstAvailable) {
      form.token_id = String(firstAvailable.id)
    }
  } catch {
    tokens.value = []
    ElMessage.error('加载 Token 失败')
  }
}

// ---------- 股票搜索 ----------
function onStockInput() {
  selectedStockSuggestion.value = null
  syncTaskNameInput()
  clearTimeout(stockSearchTimer)
  if (!stockCode.value.trim()) {
    stockSearchResults.value = []
    stockSearchPanelOpen.value = false
    return
  }
  stockSearchTimer = setTimeout(() => {
    fetchStockSuggestions(stockCode.value.trim())
  }, STOCK_SEARCH_DEBOUNCE_MS)
}

async function searchStockSuggestionsNow() {
  clearTimeout(stockSearchTimer)
  await fetchStockSuggestions(stockCode.value.trim())
  stockSearchPanelOpen.value = true
}

async function fetchStockSuggestions(keyword) {
  const trimmedKeyword = String(keyword || '').trim()
  if (!trimmedKeyword) {
    stockSearchResults.value = []
    stockSearchPanelOpen.value = false
    return
  }

  try {
    const data = await searchStocks({
      q: trimmedKeyword,
      market_type: normalizeMarketTypeValue(form.market_type),
    })
    stockSearchResults.value = (data && data.results) || []
    stockSearchPanelOpen.value = true
  } catch (error) {
    stockSearchResults.value = []
    stockSearchPanelOpen.value = true
    ElMessage.error(error.message || '股票搜索失败')
  }
}

function selectStock(item) {
  if (!item) {
    return
  }
  stockCode.value = item.code || ''
  selectedStockSuggestion.value = item
  form.market_type = normalizeMarketTypeValue(item.market_type)
  syncCommissionWithMarketType(form.market_type)
  syncTaskNameInput(true)
  stockSearchPanelOpen.value = true
}

// ---------- 提交 ----------
function buildPayload() {
  const sheetConfig = {
    spreadsheet_id: spreadsheetId.value,
    sheet_name: selectedWorksheetName.value,
    title: sheetTitle.value,
  }
  if (resolvedModelVersion.value === 'c7') {
    sheetConfig.c7_model_version = currentC7ModelVersion.value
  }
  if (selectedGoogleSheetId.value) {
    sheetConfig.google_sheet_id = selectedGoogleSheetId.value
  }

  const config = {
    sheet: sheetConfig,
    stock_code: stockCode.value.trim().toUpperCase(),
    market_type: normalizeMarketTypeValue(form.market_type),
    kline_adjustment: form.kline_adjustment || 'forward',
    kline_data_source: form.kline_data_source || 'akshare',
    price_mode: form.price_mode || 'vwap_price',
    token_type: 'file',
    token_id: Number(form.token_id),
    parameters: collectParameters(),
    recent_years: useRecentYears.value ? getCheckedRecentYears() : [],
    full_years: useFullYears.value ? getCheckedFullYears() : [],
  }
  if (form.end_date) {
    config.end_date = form.end_date
  }
  if (selectedStockSuggestion.value) {
    config.stock_name = selectedStockSuggestion.value.name || undefined
    config.exchange_market = selectedStockSuggestion.value.market || undefined
    config.security_type_name = selectedStockSuggestion.value.security_type_name || undefined
    config.stock_source = selectedStockSuggestion.value.source || undefined
  }
  if (currentExcelImport.value) {
    config.excel_import = currentExcelImport.value
  }
  return config
}

async function submit() {
  if (submitting.value) {
    return
  }

  // 与静态版一致：提交名始终取自动生成名（输入框仅作展示同步）
  const taskName = buildDefaultTaskName()
  const code = stockCode.value.trim().toUpperCase()

  if (!taskName) {
    ElMessage.error('请填写任务名称')
    return
  }
  if (!spreadsheetId.value) {
    ElMessage.error('请选择并识别单品回测 Google Sheet')
    return
  }
  if (!code) {
    ElMessage.error('请输入股票代码')
    return
  }
  if (code.includes(',') || code.includes('，')) {
    ElMessage.error('当前仅支持单个股票代码')
    return
  }
  if (!form.token_id) {
    ElMessage.error('请选择回测 Token')
    return
  }
  if (!collectParameters().length) {
    ElMessage.error('请至少填写一组参数')
    return
  }
  if (!sheetTitle.value) {
    ElMessage.error('请先识别链接或导入 Excel')
    return
  }
  if (!selectedWorksheetName.value) {
    ElMessage.error('未识别到可用工作表')
    return
  }

  submitting.value = true
  try {
    const data = await createTask({
      name: taskName,
      description: `backtest training task for ${sheetTitle.value.trim() || 'sheet'}`,
      task_type: 'backtest_training',
      config: buildPayload(),
    })
    if (!data.task_id) {
      throw new Error('任务创建失败')
    }
    ElMessage.success('任务创建成功')
    router.push('/backtest/list')
  } catch (error) {
    ElMessage.error(error.message || '任务创建失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 全局点击关闭下拉 ----------
function handleDocumentClick(event) {
  if (sheetSelectorShellRef.value && !sheetSelectorShellRef.value.contains(event.target)) {
    presetSheetPanelOpen.value = false
  }
  if (stockSearchShellRef.value && !stockSearchShellRef.value.contains(event.target)) {
    stockSearchPanelOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  loadStockMarkets()
  loadTokens()
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
  clearTimeout(stockSearchTimer)
})
</script>

<style scoped>
.full-width {
  width: 100%;
}

.backtest-create-page__search-wrap {
  position: relative;
}

.backtest-create-page__search-panel {
  position: absolute;
  z-index: 20;
  width: 100%;
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--app-shadow-soft);
}

.backtest-create-page__search-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
}

.backtest-create-page__search-item:last-child {
  border-bottom: none;
}

.backtest-create-page__search-item:hover {
  background: rgba(30, 64, 175, 0.06);
}

.backtest-create-page__panel-note {
  padding: 10px 12px;
}

.backtest-create-page__search-code,
.backtest-create-page__card-title,
.backtest-create-page__option-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-create-page__sheet-banner {
  margin-bottom: 12px;
}

.backtest-create-page__sheet-banner :deep(.el-tag) {
  margin-right: 8px;
}

.backtest-create-page__year-card {
  margin-top: 8px;
}

.backtest-create-page__year-head {
  margin-bottom: 8px;
}

.backtest-create-page__option-title {
  margin-bottom: 8px;
}

.backtest-create-page__years-display {
  margin-top: 8px;
}

.backtest-create-page__param-actions {
  flex-wrap: wrap;
  gap: 8px;
}

.backtest-create-page__help p {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.6;
}

.backtest-create-page__help p:last-child {
  margin-bottom: 0;
}

.backtest-create-page__status-success {
  color: #16a34a;
}

.backtest-create-page__status-danger {
  color: #dc2626;
}

.backtest-create-page__empty {
  padding: 24px;
}
</style>
