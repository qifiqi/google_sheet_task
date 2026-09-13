<template>
  <div class="app-page backtest-multi-create-page">
    <PageToolbar
      eyebrow="Multi-Product Builder"
      title="创建多品数据回测"
      description="每个产品独立 Sheet，参数按行号对齐，比例按百分数参与加权计算。"
    >
      <template #actions>
        <el-button @click="$router.push('/backtest-multi/list')">返回列表</el-button>
        <el-button type="primary" :loading="creating" @click="createTask">创建任务</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">基础配置</h3>
      </div>
      <el-row :gutter="16">
        <el-col :xs="24" :md="3">
          <el-form-item label="任务名称">
            <div class="static-field">按组合产品名自动拼接</div>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="2">
          <el-form-item label="K线开始日期">
            <el-date-picker
              v-model="startDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="开始日期"
              class="full-width"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="2">
          <el-form-item label="K线结束日期">
            <el-date-picker
              v-model="endDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="结束日期"
              class="full-width"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="5">
          <el-form-item label="回测 Token">
            <el-select v-model="tokenId" class="full-width" placeholder="加载中...">
              <el-option
                v-for="token in tokens"
                :key="token.id"
                :value="String(token.id)"
                :label="`${token.name} | 占用 ${token.current_in_use_count || 0}`"
              />
            </el-select>
            <div class="panel-note">仅展示回测可用的 Token（启用且未达占用上限）。</div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="4">
          <el-form-item label="比例合计">
            <el-tag size="large" type="success">{{ ratioTotalText }}</el-tag>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :xs="24" :md="8">
          <el-form-item label="全局 Google Sheet 链接">
            <el-input
              v-model="globalSheetUrl"
              autocomplete="off"
              placeholder="粘贴链接后，下方未填链接的产品自动继承（可单独覆盖）"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="4">
          <el-form-item label="市场">
            <el-select v-model="globalMarketType" class="full-width">
              <el-option v-for="market in stockMarkets" :key="market.value" :value="market.value" :label="market.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="3">
          <el-form-item label="K线复权">
            <el-select v-model="globalKlineAdjustment" class="full-width">
              <el-option value="forward" label="前复权" />
              <el-option value="back" label="后复权" />
              <el-option value="none" label="不复权" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="4">
          <el-form-item label="价格模式">
            <el-select v-model="globalPriceMode" class="full-width">
              <el-option v-for="option in PRICE_MODE_OPTIONS" :key="option.value" :value="option.value" :label="option.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="5">
          <el-form-item label="K线数据源">
            <el-select v-model="globalKlineDataSource" class="full-width">
              <el-option v-for="option in KLINE_SOURCE_OPTIONS" :key="option.value" :value="option.value" :label="option.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <div class="panel-note">
            以上全局设置会自动应用到全部产品；产品卡片内单独修改后，该字段不再跟随全局变化。
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card
      v-for="(product, pIndex) in products"
      :key="product.key"
      shadow="never"
      class="page-section backtest-multi-create-page__product-card"
    >
      <div class="section-heading">
        <div>
          <div class="backtest-multi-create-page__card-title">
            <el-tag size="small" type="primary">{{ product.model_version.toUpperCase() }}</el-tag>
            <span class="section-title section-title--muted">{{ product.product_name || `产品 ${pIndex + 1}` }}</span>
          </div>
          <div class="panel-note">
            {{ product.stock_code.trim().toUpperCase() || '未填写' }} · {{ formatMarketLabel(product.market_type) }} · 比例 {{ product.ratio ?? 0 }}%
          </div>
        </div>
        <div class="section-actions">
          <el-switch v-model="product.is_fixed" active-text="固定" />
          <el-button type="danger" plain size="small" @click="removeProduct(pIndex)">删除产品</el-button>
        </div>
      </div>

      <el-row :gutter="16">
        <el-col :xs="24" :md="6">
          <el-form-item label="产品名称">
            <el-input v-model="product.product_name" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="4">
          <el-form-item label="股票代码">
            <div class="backtest-multi-create-page__search-wrap">
              <el-input
                v-model="product.stock_code"
                autocomplete="off"
                @input="onStockInput(product)"
              />
              <div v-if="product.stockSearchOpen" class="backtest-multi-create-page__search-panel">
                <template v-if="product.stockSearchItems.length">
                  <div
                    v-for="stock in product.stockSearchItems"
                    :key="`${stock.code}-${stock.market || ''}`"
                    class="backtest-multi-create-page__search-item"
                    @mousedown.prevent="selectStock(product, stock)"
                  >
                    <div class="backtest-multi-create-page__search-code">{{ stock.code }}</div>
                    <div class="panel-note">{{ stock.label || stock.name || '' }}</div>
                  </div>
                </template>
                <div v-else class="panel-note backtest-multi-create-page__search-empty">暂无匹配结果</div>
              </div>
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="3">
          <el-form-item label="市场">
            <el-select v-model="product.market_type" class="full-width" @change="onMarketChange(product)">
              <el-option v-for="market in stockMarkets" :key="market.value" :value="market.value" :label="market.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="3">
          <el-form-item label="K线复权">
            <el-select v-model="product.kline_adjustment" class="full-width" @change="product.touched.kline = true">
              <el-option value="forward" label="前复权" />
              <el-option value="back" label="后复权" />
              <el-option value="none" label="不复权" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="4">
          <el-form-item label="价格模式">
            <el-select v-model="product.price_mode" class="full-width" @change="product.touched.priceMode = true">
              <el-option v-for="option in PRICE_MODE_OPTIONS" :key="option.value" :value="option.value" :label="option.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="4">
          <el-form-item label="K线数据源">
            <el-select v-model="product.kline_data_source" class="full-width" @change="product.touched.source = true">
              <el-option v-for="option in KLINE_SOURCE_OPTIONS" :key="option.value" :value="option.value" :label="option.label" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="12" :md="3">
          <el-form-item label="比例 %">
            <el-input-number
              v-model="product.ratio"
              :min="0"
              :step="0.0001"
              :controls="false"
              class="full-width"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Google Sheet 链接">
            <el-input
              v-model="product.sheet_url"
              autocomplete="off"
              placeholder="留空继承顶部全局链接"
              @input="onSheetUrlInput(product)"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <div :class="['panel-note', `sheet-info--${product.sheetInfo.type || 'muted'}`]">
        {{ product.sheetInfo.text }}
      </div>

      <div class="backtest-multi-create-page__param-toolbar">
        <el-button size="small" @click="addParameterRow(product)">添加参数行</el-button>
        <el-button size="small" :loading="product.pasteBusy" @click="pasteParametersFromClipboard(product)">粘贴追加</el-button>
        <el-button size="small" :loading="product.copyBusy" @click="copyParametersToClipboard(product)">复制参数</el-button>
        <el-popover placement="top" trigger="focus" :width="420" title="粘贴与复制说明">
          <template #reference>
            <el-button size="small" circle>?</el-button>
          </template>
          <div class="backtest-multi-create-page__param-help">
            <div><strong>C3 粘贴</strong>：每行 6 列时按不含手续费处理，系统按当前市场自动补手续费（A股 0.035%，美股 0.002%）；每行 7 列时第 1 列按手续费处理。</div>
            <div><strong>C3 复制</strong>：复制当前表格为 Tab 分隔行，包含 <code>Commission</code> 和后续参数列，可直接贴到其他产品或 Excel。</div>
            <div><strong>C5 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
            <div><strong>C7 粘贴/复制</strong>：每行 2 列，顺序为 <code>X Multiplier</code>、<code>ML</code>。</div>
          </div>
        </el-popover>
        <span :class="['panel-note', product.paramStatus.type ? `sheet-info--${product.paramStatus.type}` : '']">
          {{ product.paramStatus.text }}
        </span>
      </div>

      <el-table v-if="paramFields(product).length" :data="product.rows" border size="small">
        <el-table-column
          v-for="(field, fIndex) in paramFields(product)"
          :key="field.key"
          :label="field.label"
          min-width="110"
        >
          <template #default="{ $index }">
            <el-input v-model="product.rows[$index][fIndex]" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="product.rows.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="backtest-multi-create-page__action-bar">
      <el-button type="primary" plain @click="addProduct()">添加产品</el-button>
      <el-button type="primary" :loading="creating" @click="createTask">创建任务</el-button>
      <span :class="['panel-note', createStatus.type ? `sheet-info--${createStatus.type}` : '']">{{ createStatus.text }}</span>
    </div>

    <el-dialog
      v-model="pasteDialog.visible"
      title="粘贴参数"
      width="640px"
      :close-on-click-modal="false"
      @closed="resolvePasteDialog('')"
    >
      <el-alert :title="pasteDialog.message" type="warning" :closable="false" class="backtest-multi-create-page__paste-alert" />
      <el-input
        v-model="pasteDialog.text"
        type="textarea"
        :rows="8"
        placeholder="在这里粘贴从 Excel 或其他任务复制的参数"
      />
      <template #footer>
        <el-button @click="pasteDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmManualPaste">追加参数</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { searchStocks } from '@/api/backtestMulti'
import { createTask as createTaskApi } from '@/api/task'
import { getWorksheets, getTokens } from '@/api/googleSheet'
import { getEnums } from '@/api/meta'
import { defaultDateRange, formatDate } from '@/utils/tradingDate'
import PageToolbar from '@/components/PageToolbar.vue'
import { useResponsive } from '@/composables/useResponsive'

const router = useRouter()
useResponsive()

// ===== 静态版 backtest_multi_product_create.js 的常量翻译 =====
const TASK_TYPE = 'backtest_multi_product'

const FIELD_MAP = {
  c3: [
    { key: 'commission', label: 'Commission' },
    { key: 'xm', label: 'X Multiplier' },
    { key: 'dbbh1', label: '单边保护1' },
    { key: 'dbbh2', label: '单边保护2' },
    { key: 'zlxc', label: '中立限仓' },
    { key: 'zsgz', label: '指数跟踪' },
    { key: 'ywf1', label: '一窝蜂 S' },
    { key: 'ywf2', label: '一窝蜂 B' }
  ],
  c5: [
    { key: 'xm', label: 'X Multiplier' },
    { key: 'ml', label: 'ML' }
  ],
  c7: [
    { key: 'xm', label: 'X Multiplier' },
    { key: 'ml', label: 'ML' }
  ]
}

const PRICE_MODE_OPTIONS = [
  { value: 'vwap_price', label: '加权平均价' },
  { value: 'kp_price', label: '开盘价' },
  { value: 'sp_price', label: '收盘价' },
  { value: 'ohlc_price', label: 'OHLC（开高低收）' }
]

const KLINE_SOURCE_OPTIONS = [
  { value: 'akshare', label: 'AKShare（默认）' },
  { value: 'dfcf', label: '东方财富' },
  { value: 'qq', label: '腾讯' },
  { value: 'yahoo', label: 'Yahoo' },
  { value: 'tdx', label: '通达信（仅A股）' }
]

// ===== 全局设置 =====
const startDate = ref('')
const endDate = ref('')
const tokenId = ref('')
const tokens = ref([])
const stockMarkets = ref([])
const globalSheetUrl = ref('')
const globalMarketType = ref('cn')
const globalKlineAdjustment = ref('forward')
const globalPriceMode = ref('sp_price')
const globalKlineDataSource = ref('akshare')

const creating = ref(false)
const createStatus = ref({ text: '', type: '' })

// ===== 粘贴参数手动弹窗（HTTPS 不可用时的降级） =====
const pasteDialog = reactive({ visible: false, message: '', text: '', resolve: null })

let productSeq = 0
let globalSheetTimer = null

function paramFields(product) {
  return FIELD_MAP[product.model_version] || FIELD_MAP.c3
}

function extractSpreadsheetId(rawUrl) {
  const match = String(rawUrl || '').trim().match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/)
  return match ? match[1] : ''
}

// Sheet 标题推断模型版本：C7 → c7；C5/C4 → c5；其余 c3（与静态版一致）。
function inferModelVersion(title) {
  const normalized = String(title || '').toUpperCase()
  if (normalized.includes('C7')) return 'c7'
  return normalized.includes('C5') || normalized.includes('C4') ? 'c5' : 'c3'
}

function formatMarketLabel(marketType) {
  return String(marketType || '').trim().toLowerCase() === 'en' ? '美股 en' : 'A股 cn'
}

function getDefaultCommissionByMarket(marketType) {
  return stockMarkets.value.find((market) => market.value === marketType)?.default_commission || ''
}

// 继承自全局设置的当前取值；产品卡片创建时作为默认值。
function getGlobalDefaults() {
  return {
    market_type: globalMarketType.value || 'cn',
    kline_adjustment: globalKlineAdjustment.value || 'forward',
    price_mode: globalPriceMode.value || 'sp_price',
    kline_data_source: globalKlineDataSource.value || 'akshare'
  }
}

// 产品 Sheet 链接的生效值：自有链接优先，留空则继承全局链接。
function getEffectiveSheetUrl(product) {
  const ownUrl = String(product.sheet_url || '').trim()
  if (ownUrl) return ownUrl
  return String(globalSheetUrl.value || '').trim()
}

// ===== 产品卡片 =====
function createProductState(defaults = {}) {
  productSeq += 1
  const inherited = { ...getGlobalDefaults(), ...defaults }
  return reactive({
    key: `product-${productSeq}-${Date.now()}`,
    product_name: inherited.product_name || `产品 ${productSeq}`,
    stock_code: inherited.stock_code || '',
    exchange_market: inherited.exchange_market || '',
    market_type: inherited.market_type || 'cn',
    kline_adjustment: inherited.kline_adjustment || 'forward',
    price_mode: inherited.price_mode || 'sp_price',
    kline_data_source: inherited.kline_data_source || 'akshare',
    ratio: inherited.ratio ?? '',
    is_fixed: Boolean(inherited.is_fixed),
    sheet_url: inherited.sheet_url || '',
    model_version: 'c3',
    rows: [],
    touched: { market: false, kline: false, priceMode: false, source: false },
    sheetStatus: 'idle',
    sheetId: '',
    sheetName: '',
    sheetTitle: '',
    lastAnalyzedId: '',
    sheetInfo: { text: '尚未识别 Sheet', type: '' },
    paramStatus: { text: '', type: '' },
    stockSearchItems: [],
    stockSearchOpen: false,
    sheetTimer: null,
    stockTimer: null,
    pasteBusy: false,
    copyBusy: false
  })
}

function addProduct(defaults = {}) {
  const product = createProductState(defaults)
  resetParameterTable(product, 'c3')
  products.value.push(product)
  if (stockMarkets.value.length) {
    scheduleSheetAnalyze(product, true)
  }
}

function removeProduct(index) {
  products.value.splice(index, 1)
}

function clearSheetMeta(product) {
  product.sheetId = ''
  product.sheetName = ''
  product.sheetTitle = ''
  product.lastAnalyzedId = ''
  product.sheetStatus = 'idle'
}

function resetParameterTable(product, version) {
  product.model_version = version
  product.rows = []
  addParameterRow(product)
}

function addParameterRow(product, values = []) {
  const fields = paramFields(product)
  const defaultCommission = getDefaultCommissionByMarket(product.market_type)
  const rowValues = Array.isArray(values) ? [...values] : []
  if (product.model_version === 'c3' && !String(rowValues[0] ?? '').trim()) {
    rowValues[0] = defaultCommission
  }
  product.rows.push(fields.map((field, index) => String(rowValues[index] ?? (field.key === 'commission' ? defaultCommission : ''))))
}

// 市场切换后，把"可复用行"（C3 除手续费列外全空；C5/C7 整行全空）的手续费同步为新市场默认值。
function syncEmptyCommissionRows(product) {
  if (product.model_version !== 'c3') return
  const defaultCommission = getDefaultCommissionByMarket(product.market_type)
  product.rows.forEach((row) => {
    if (isReusableParameterRow(product, row)) {
      row[0] = defaultCommission
    }
  })
}

function isReusableParameterRow(product, row) {
  const values = Array.isArray(row) ? row : []
  if (product.model_version !== 'c3') {
    return values.every((value) => !String(value ?? '').trim())
  }
  return values.slice(1).every((value) => !String(value ?? '').trim())
}

function collectParameterRows(product) {
  const version = product.model_version || 'c3'
  return product.rows
    .map((row) => row.map((value) => String(value ?? '').trim()))
    .filter((row) => (version === 'c3' ? row.slice(1).some(Boolean) : row.some(Boolean)))
}

// Sheet 标题含 C7.0.3 时价格模式默认切换为 OHLC，其余回默认收盘价；
// 用户手动改过价格模式后不再自动切换。
function applyPriceModeDefault(product, title) {
  if (product.touched.priceMode) return
  const isC703 = String(title || '').toUpperCase().includes('C7.0.3')
  product.price_mode = isC703 ? 'ohlc_price' : 'sp_price'
}

function onSheetUrlInput(product) {
  scheduleSheetAnalyze(product)
}

function scheduleSheetAnalyze(product, immediate = false) {
  const spreadsheetId = extractSpreadsheetId(getEffectiveSheetUrl(product))
  if (product.lastAnalyzedId && product.lastAnalyzedId !== spreadsheetId) {
    clearSheetMeta(product)
    product.sheetInfo = { text: spreadsheetId ? '等待自动识别 Sheet...' : '尚未识别 Sheet', type: '' }
  }
  clearTimeout(product.sheetTimer)
  product.sheetTimer = setTimeout(() => analyzeSheet(product), immediate ? 0 : 500)
}

async function analyzeSheet(product) {
  const ownUrl = String(product.sheet_url || '').trim()
  const spreadsheetId = extractSpreadsheetId(getEffectiveSheetUrl(product))
  if (!spreadsheetId) {
    clearSheetMeta(product)
    product.sheetInfo = ownUrl
      ? { text: '未识别到有效的 Google Sheet 链接', type: 'danger' }
      : { text: '尚未识别 Sheet（可留空继承顶部全局链接）', type: '' }
    return
  }
  if (product.sheetStatus === 'success' && product.lastAnalyzedId === spreadsheetId) {
    return
  }

  product.sheetStatus = 'loading'
  product.sheetInfo = { text: '正在自动识别 Sheet...', type: 'primary' }
  try {
    const data = await getWorksheets({ spreadsheet_id: spreadsheetId })
    const sheetName = Array.isArray(data.worksheets) && data.worksheets.length ? data.worksheets[0] : 'data'
    const title = data.title || ''
    product.sheetId = spreadsheetId
    product.sheetName = sheetName
    product.sheetTitle = title
    product.lastAnalyzedId = spreadsheetId
    product.sheetStatus = 'success'
    const nextVersion = inferModelVersion(title)
    if (product.model_version !== nextVersion) {
      resetParameterTable(product, nextVersion)
    }
    applyPriceModeDefault(product, title)
    product.sheetInfo = { text: `${title || spreadsheetId} / ${sheetName}`, type: 'success' }
  } catch (error) {
    clearSheetMeta(product)
    product.sheetInfo = { text: error.message || '识别失败', type: 'danger' }
  }
}

// ===== 股票搜索 =====
function onStockInput(product) {
  product.exchange_market = ''
  clearTimeout(product.stockTimer)
  const keyword = product.stock_code.trim()
  if (!keyword) {
    product.stockSearchItems = []
    product.stockSearchOpen = false
    return
  }
  product.stockTimer = setTimeout(async () => {
    try {
      const data = await searchStocks({ q: keyword, market_type: product.market_type })
      product.stockSearchItems = Array.isArray(data?.results) ? data.results : []
      product.stockSearchOpen = true
    } catch (error) {
      product.stockSearchItems = []
      product.stockSearchOpen = false
      ElMessage.error(error.message || '搜索失败')
    }
  }, 600)
}

// 选中联想项：回填产品名/市场/exchange_market，并按新市场补手续费。
function selectStock(product, stock) {
  product.stock_code = stock.code || ''
  product.product_name = stock.name || stock.code || ''
  product.market_type = stock.market_type || product.market_type || 'cn'
  product.exchange_market = stock.market || ''
  product.touched.market = true
  product.stockSearchItems = []
  product.stockSearchOpen = false
  syncEmptyCommissionRows(product)
}

function onMarketChange(product) {
  product.touched.market = true
  syncEmptyCommissionRows(product)
}

// ===== 全局设置联动（产品未手动改动的字段跟随全局） =====
function applyGlobalSettingsToProducts() {
  products.value.forEach((product) => {
    if (!product.touched.market && product.market_type !== globalMarketType.value) {
      product.market_type = globalMarketType.value
      syncEmptyCommissionRows(product)
    }
    if (!product.touched.kline) {
      product.kline_adjustment = globalKlineAdjustment.value
    }
    if (!product.touched.priceMode) {
      product.price_mode = globalPriceMode.value
    }
    if (!product.touched.source) {
      product.kline_data_source = globalKlineDataSource.value
    }
    if (!String(product.sheet_url || '').trim()) {
      scheduleSheetAnalyze(product)
    }
  })
}

watch(globalMarketType, applyGlobalSettingsToProducts)
watch(globalKlineAdjustment, applyGlobalSettingsToProducts)
watch(globalPriceMode, applyGlobalSettingsToProducts)
watch(globalKlineDataSource, applyGlobalSettingsToProducts)
watch(globalSheetUrl, () => {
  clearTimeout(globalSheetTimer)
  globalSheetTimer = setTimeout(applyGlobalSettingsToProducts, 500)
})

// ===== 参数粘贴 / 复制 =====
function parseParameterClipboard(raw) {
  return String(raw || '')
    .split(/\r?\n/)
    .map((line) => line.split(/\t|,/).map((item) => item.trim()))
    .filter((row) => row.some(Boolean))
}

function normalizePastedParameterRow(product, row) {
  const values = row.map((item) => String(item ?? '').trim())
  if (product.model_version !== 'c3') {
    return values
  }
  const defaultCommission = getDefaultCommissionByMarket(product.market_type)
  if (values.length === 6) {
    return [defaultCommission, ...values]
  }
  if (values.length === 7) {
    values[0] = values[0] || defaultCommission
    return values
  }
  return values
}

function parameterRowsToClipboard(product) {
  return collectParameterRows(product)
    .map((row) => row.join('\t'))
    .join('\n')
}

function openManualPasteDialog(message) {
  return new Promise((resolve) => {
    pasteDialog.message = message
    pasteDialog.text = ''
    pasteDialog.resolve = resolve
    pasteDialog.visible = true
  })
}

function resolvePasteDialog(value) {
  if (pasteDialog.resolve) {
    pasteDialog.resolve(value ?? '')
    pasteDialog.resolve = null
  }
}

function confirmManualPaste() {
  const value = pasteDialog.text
  pasteDialog.visible = false
  resolvePasteDialog(value)
}

async function readClipboardText() {
  const canUseClipboardApi = window.isSecureContext && navigator.clipboard?.readText
  if (!canUseClipboardApi) {
    return openManualPasteDialog('当前页面不是 HTTPS，浏览器无法授予剪切板读取权限。请在下方粘贴参数后继续。')
  }
  try {
    return await navigator.clipboard.readText()
  } catch {
    return openManualPasteDialog('未完成剪切板权限授权，或浏览器暂时无法读取剪切板。请在下方粘贴参数后继续。')
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

async function pasteParametersFromClipboard(product) {
  product.pasteBusy = true
  try {
    const raw = await readClipboardText()
    const rows = parseParameterClipboard(raw)
    if (!rows.length) {
      throw new Error('剪切板中没有可追加的参数行')
    }
    rows.forEach((row) => {
      const normalizedRow = normalizePastedParameterRow(product, row)
      const reusableIndex = product.rows.findIndex((rowItem) => isReusableParameterRow(product, rowItem))
      if (reusableIndex >= 0) {
        const fields = paramFields(product)
        product.rows[reusableIndex] = fields.map((field, index) => {
          const value = normalizedRow[index]
          return String(value ?? (field.key === 'commission' ? getDefaultCommissionByMarket(product.market_type) : ''))
        })
        return
      }
      addParameterRow(product, normalizedRow)
    })
    product.paramStatus = { text: `已追加 ${rows.length} 行参数`, type: 'success' }
  } catch (error) {
    ElMessage.error(error.message || '读取剪切板失败')
  } finally {
    product.pasteBusy = false
  }
}

async function copyParametersToClipboard(product) {
  product.copyBusy = true
  try {
    const text = parameterRowsToClipboard(product)
    if (!text) {
      throw new Error('当前产品没有可复制的参数')
    }
    await writeClipboardText(text)
    product.paramStatus = { text: '参数已复制，可直接粘贴到其他产品或 Excel', type: 'success' }
  } catch (error) {
    ElMessage.error(error.message || '复制失败')
  } finally {
    product.copyBusy = false
  }
}

// ===== 任务组装与创建 =====
const ratioTotalText = computed(() => {
  const total = products.value.reduce((sum, product) => {
    const value = Number(product.ratio || 0)
    return sum + (Number.isFinite(value) ? value : 0)
  }, 0)
  return `${Number(total.toFixed(4))}%`
})

function collectProducts() {
  return products.value.map((product, index) => ({
    product_index: index,
    product_name: String(product.product_name || '').trim() || `产品 ${index + 1}`,
    stock_code: String(product.stock_code || '').trim().toUpperCase(),
    market_type: product.market_type,
    exchange_market: product.exchange_market || undefined,
    kline_adjustment: product.kline_adjustment || 'forward',
    kline_data_source: product.kline_data_source || 'akshare',
    price_mode: product.price_mode || 'sp_price',
    ratio: String(product.ratio ?? '').trim(),
    is_fixed: Boolean(product.is_fixed),
    sheet: {
      spreadsheet_id: product.sheetStatus === 'success' ? product.sheetId : '',
      sheet_name: product.sheetName || 'data',
      title: product.sheetTitle || ''
    },
    parameters: collectParameterRows(product)
  }))
}

function buildTaskProductGroups(items) {
  const fixedProducts = items.filter((product) => product.is_fixed)
  const activeProducts = items.filter((product) => !product.is_fixed)
  if (fixedProducts.length && activeProducts.length) {
    return activeProducts.map((activeProduct) => [...fixedProducts, activeProduct]
      .map((product, index) => ({ ...JSON.parse(JSON.stringify(product)), product_index: index })))
  }
  return [items.map((product, index) => ({ ...JSON.parse(JSON.stringify(product)), product_index: index }))]
}

function buildBatchId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID()
  }
  return `batch-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function buildTaskName(groupProducts) {
  return groupProducts.map((product, index) => (
    product.product_name?.trim() || product.stock_code?.trim() || `产品 ${index + 1}`
  )).join('-')
}

function validatePayload(items) {
  if (items.length < 2) {
    throw new Error('至少需要 2 个产品')
  }
  const expectedRows = items[0].parameters.length
  items.forEach((product, index) => {
    const state = products.value[index]
    if (!product.stock_code) throw new Error(`产品 ${index + 1} 缺少股票代码`)
    if (state?.sheetStatus === 'loading') throw new Error(`产品 ${index + 1} 的 Google Sheet 正在识别，请稍后`)
    if (state?.sheetStatus !== 'success') throw new Error(`产品 ${index + 1} 的 Google Sheet 尚未自动识别成功`)
    if (!product.sheet.spreadsheet_id) throw new Error(`产品 ${index + 1} 缺少 Google Sheet`)
    if (!product.parameters.length) throw new Error(`产品 ${index + 1} 缺少参数`)
    if (product.parameters.length !== expectedRows) throw new Error('所有产品参数行数必须一致')
  })
}

async function createTask() {
  createStatus.value = { text: '', type: '' }
  creating.value = true
  try {
    const items = collectProducts()
    validatePayload(items)
    const taskGroups = buildTaskProductGroups(items)
    const batchId = buildBatchId()
    if (!startDate.value || !endDate.value) throw new Error('请选择 K 线数据时间范围')
    if (!tokenId.value) throw new Error('请选择回测 Token')

    for (let index = 0; index < taskGroups.length; index += 1) {
      const groupProducts = taskGroups[index]
      createStatus.value = { text: `正在创建 ${index + 1}/${taskGroups.length}`, type: '' }
      await createTaskApi({
        name: buildTaskName(groupProducts),
        description: 'multi product backtest task',
        task_type: TASK_TYPE,
        config: {
          start_date: startDate.value,
          end_date: endDate.value,
          token_type: 'file',
          token_id: Number(tokenId.value),
          fixed_product_batch_id: batchId,
          // 旧版累计收益直接加权算法已停用，固定使用日收益加权后复利。
          weighting_mode: 'daily_compound',
          products: groupProducts
        }
      })
    }
    router.push('/backtest-multi/list')
  } catch (error) {
    createStatus.value = { text: error.message || '任务创建失败', type: 'danger' }
    ElMessage.error(error.message || '任务创建失败')
  } finally {
    creating.value = false
  }
}

async function loadBacktestTokens() {
  try {
    const data = await getTokens({ task_type: 'backtest_training' })
    const allTokens = Array.isArray(data.tokens) ? data.tokens : []
    // 只展示回测可用的 Token：启用且未达到最大占用。
    tokens.value = allTokens.filter((token) => token.is_active && token.is_available)
  } catch {
    tokens.value = []
  }
}

async function loadStockMarkets() {
  const payload = await getEnums()
  stockMarkets.value = payload?.stock_markets || []
  if (!stockMarkets.value.length) throw new Error('市场枚举为空')
}

onMounted(async () => {
  const range = defaultDateRange(3)
  endDate.value = formatDate(range.end)
  startDate.value = formatDate(range.start)
  loadBacktestTokens()
  try {
    await loadStockMarkets()
    addProduct({ ratio: 50 })
    addProduct({ ratio: 50 })
  } catch (error) {
    createStatus.value = { text: error.message || '市场枚举加载失败', type: 'danger' }
    ElMessage.error(error.message || '市场枚举加载失败')
  }
})

onBeforeUnmount(() => {
  products.value.forEach((product) => {
    clearTimeout(product.sheetTimer)
    clearTimeout(product.stockTimer)
  })
  clearTimeout(globalSheetTimer)
})
</script>

<style scoped>
.full-width {
  width: 100%;
}

.static-field {
  padding: 0 12px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface);
  color: var(--app-text-muted, #94a3b8);
  font-size: 13px;
  line-height: 32px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.backtest-multi-create-page__product-card {
  position: relative;
}

.backtest-multi-create-page__card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backtest-multi-create-page__search-wrap {
  position: relative;
}

.backtest-multi-create-page__search-panel {
  position: absolute;
  z-index: 20;
  width: 100%;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--app-shadow-soft);
}

.backtest-multi-create-page__search-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
}

.backtest-multi-create-page__search-item:last-child {
  border-bottom: none;
}

.backtest-multi-create-page__search-code {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-create-page__search-empty {
  padding: 10px 12px;
}

.backtest-multi-create-page__param-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.backtest-multi-create-page__param-help {
  display: grid;
  gap: 6px;
  font-size: 12px;
  line-height: 1.6;
}

.backtest-multi-create-page__action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.backtest-multi-create-page__paste-alert {
  margin-bottom: 12px;
}

.sheet-info--success {
  color: #16a34a;
}

.sheet-info--danger {
  color: #dc2626;
}

.sheet-info--primary {
  color: #2563eb;
}
</style>
