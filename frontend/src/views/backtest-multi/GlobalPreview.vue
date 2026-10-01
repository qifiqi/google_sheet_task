<template>
  <div class="app-page backtest-multi-preview-page">
    <PageToolbar
      eyebrow="Multi-Product Preview"
      title="多产品全局预览"
      :description="headDescription"
    >
      <template #actions>
        <el-button @click="exportXlsx">导出 XLSX</el-button>
        <el-button @click="exportSeries">导出收益序列</el-button>
        <el-button type="primary" plain @click="openExportWordModal">导出 Word</el-button>
        <el-button class="page-back-button" @click="$router.push({ path: `/backtest-multi/${taskId}`, query: pagingQuery })">返回详情</el-button>
      </template>
    </PageToolbar>

    <el-row :gutter="12" class="backtest-multi-preview-page__metrics">
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">任务 ID</div>
          <div class="backtest-multi-preview-page__metric-id font-mono">{{ taskId }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">产品数</div>
          <div class="backtest-multi-preview-page__metric-value">{{ summary.product_count ?? 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">参数分组</div>
          <div class="backtest-multi-preview-page__metric-value">{{ summary.group_count ?? 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="sub-card">
          <div class="panel-note">成功结果</div>
          <div class="backtest-multi-preview-page__metric-value backtest-multi-preview-page__metric-value--success">
            {{ summary.success_results ?? 0 }}
          </div>
        </div>
      </el-col>
    </el-row>

    <div v-loading="loading" class="backtest-multi-preview-page__layout">
      <!-- Group Selector -->
      <el-card v-if="groups.length" shadow="never" class="page-section">
        <el-row :gutter="16" align="bottom">
          <el-col :xs="24" :md="6">
            <el-form-item label="参数方案">
              <el-select v-model="activeGroupKey" class="full-width" @change="onGroupChange">
                <el-option
                  v-for="group in groups"
                  :key="group.group_key"
                  :value="group.group_key"
                  :label="`${group.group_label} (${group.result_count || 0} 个产品结果)`"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="8">
            <el-form-item label="无风险利率（年化%）">
              <el-input-number
                v-model="riskFreePercent"
                :min="0"
                :max="100"
                :step="0.01"
                :controls="false"
                class="full-width"
              />
              <div class="panel-note">
                影响夏普/索提诺比率（比例计算两列与导出报告）；单品「指数 / 模型结果」列是回测执行结果，不参与重算。
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-card>

      <!-- Ratio Editing -->
      <el-card v-if="products.length" shadow="never" class="page-section">
        <div class="section-heading">
          <h3 class="section-title section-title--muted">产品比例调整</h3>
          <div class="section-actions">
            <el-tag type="success">{{ ratioStatusText }}</el-tag>
            <el-button size="small" type="warning" :loading="calculating" @click="applyRatioPreview">计算预览</el-button>
            <el-button size="small" type="primary" :loading="savingRatios" @click="saveRatios">保存比例</el-button>
          </div>
        </div>
        <div class="backtest-multi-preview-page__ratio-formula-hint">
          <div><span class="backtest-multi-preview-page__hint-title">比例计算：</span>先将累计收益率转换为当天收益率，按比例合成后复利还原为组合累计收益率，再重新计算组合指标。</div>
          <div class="backtest-multi-preview-page__hint-note">比例计算-指数来自组合 index_return，比例计算-结果来自组合 start_return；导出也使用同一套后端计算。</div>
        </div>
        <el-table :data="ratioRows" size="small">
          <el-table-column label="产品" min-width="160">
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column label="股票/市场" min-width="140">
            <template #default="{ row }">{{ row.stockMarket }}</template>
          </el-table-column>
          <el-table-column label="比例(%)" width="220">
            <template #default="{ row }">
              <el-input-number
                :model-value="ratioValues[row.index]"
                :min="0"
                :step="0.0001"
                :controls="false"
                size="small"
                class="backtest-multi-preview-page__ratio-input"
                @update:model-value="(value) => updateRatio(row.index, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="180">
            <template #default="{ row }">
              <span class="panel-note">{{ row.ratio > 0 ? '参与计算' : '比例为 0，不参与组合与展示' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Data Table -->
      <el-card shadow="never" class="page-section">
        <div v-if="!activeGroup || !activeGroup.rows?.length" class="panel-note panel-note--center backtest-multi-preview-page__empty">
          {{ emptyText }}
        </div>

        <div v-else class="backtest-multi-preview-page__table-wrap">
          <table class="backtest-multi-preview-page__table">
            <thead>
              <tr class="backtest-multi-preview-page__product-row">
                <td class="sticky-col sticky-col-1"></td>
                <td class="sticky-col sticky-col-2"></td>
                <td
                  v-for="item in visibleProducts"
                  :key="`p-${item.index}`"
                  colspan="3"
                >{{ item.product.product_name || item.product.stock_code || '产品' }}</td>
                <td colspan="2"></td>
              </tr>
              <tr>
                <th class="sticky-col sticky-col-1">指标类型</th>
                <th class="sticky-col sticky-col-2">指标</th>
                <template v-for="item in visibleProducts" :key="`h-${item.index}`">
                  <th>指数</th>
                  <th>模型结果</th>
                  <th>模型结果（{{ formatRatioHeader(item.product.ratio) }}）</th>
                </template>
                <th>比例计算-指数</th>
                <th>比例计算-结果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in activeGroup.rows" :key="index">
                <td class="sticky-col sticky-col-1 backtest-multi-preview-page__sticky-main">
                  {{ row.category || '-' }}
                </td>
                <td class="sticky-col sticky-col-2">{{ row.metric || '-' }}</td>
                <template v-for="item in visibleProducts" :key="`c-${item.index}`">
                  <td>{{ cellValue(row, item.index, 'index_value') }}</td>
                  <td>{{ cellValue(row, item.index, 'result_value') }}</td>
                  <td>{{ cellValue(row, item.index, 'weighted_result_value') }}</td>
                </template>
                <td>{{ row.weighted_index_value || '-' }}</td>
                <td>{{ row.weighted_result_value || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </el-card>
    </div>

    <!-- 导出 Word 选股弹窗（多选+比例；组合指数是否并列由开关控制，默认开启） -->
    <el-dialog v-model="wordModalVisible" title="导出 Word · 选择股票" width="560px">
      <div class="backtest-multi-preview-page__word-head">
        <span class="panel-note">点击股票添加为指数列（可多选、可同股不同比例）</span>
        <span class="panel-note">已选 {{ benchmarkEntries.length }} 条</span>
      </div>
      <el-form-item label="包含组合指数">
        <el-switch v-model="includeCompositeBenchmark" />
        <span class="panel-note">全部产品按比例组合作为一个基准列，列头显示"指数"</span>
      </el-form-item>
      <!-- 已选基准区：每条 = 基准名 + 比例输入 + 删除；支持同股不同比例多条 -->
      <div class="backtest-multi-preview-page__benchmark-list">
        <div v-if="!benchmarkEntries.length" class="panel-note">
          未选择自定义指数（点击下方股票添加）；组合指数由上方开关控制
        </div>
        <div
          v-for="(entry, index) in benchmarkEntries"
          :key="`${entry.code}-${index}`"
          class="backtest-multi-preview-page__benchmark-row"
        >
          <span class="backtest-multi-preview-page__benchmark-code">{{ entry.code }}</span>
          <el-input-number
            :model-value="entry.ratio"
            :min="0.5"
            :max="100"
            :step="0.5"
            :controls="false"
            size="small"
            @update:model-value="(value) => updateBenchmarkRatio(entry, value)"
          />
          <span class="panel-note">%</span>
          <el-button link type="danger" size="small" @click="removeBenchmark(index)">删除</el-button>
        </div>
      </div>
      <!-- 股票列表：点击添加为基准；再次点击可用不同比例叠加 -->
      <el-input
        v-model="stockSearch"
        placeholder="搜索股票名称 / 代码"
        clearable
        class="backtest-multi-preview-page__word-search"
      />
      <div class="backtest-multi-preview-page__stock-list">
        <div class="panel-note">组合指数由上方开关控制；未选股票时始终包含组合指数</div>
        <div v-if="!stockOptions.length" class="panel-note">暂无可选股票</div>
        <div
          v-for="item in stockOptions"
          :key="item.code"
          class="backtest-multi-preview-page__stock-row"
          title="点击添加为基准；再次点击可用不同比例叠加"
          @click="addBenchmark(item.code)"
        >
          <span>{{ item.name }} ({{ item.code }})</span>
          <el-tag v-if="stockEntryCount(item.code)" size="small" type="info">
            ×{{ stockEntryCount(item.code) }}
          </el-tag>
          <small class="panel-note">比例 {{ item.ratio }}%</small>
          <el-icon><Plus /></el-icon>
        </div>
      </div>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="价格类型">
            <el-select v-model="wordPriceType" class="full-width">
              <el-option value="" label="跟随任务（默认）" />
              <el-option value="sp_price" label="收盘价" />
              <el-option value="kp_price" label="开盘价" />
              <el-option value="vwap_price" label="加权平均价" />
              <el-option value="ohlc_price" label="OHLC（开高低收）" />
              <el-option value="random_price" label="随机价" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="无风险利率（年化%）">
            <el-input-number
              v-model="wordRiskFreePercent"
              :min="0"
              :max="100"
              :step="0.01"
              :controls="false"
              class="full-width"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <div class="panel-note">
        价格类型仅展示在报告信息中；无风险利率用于夏普比率重算并展示，打开弹窗时默认跟随页面上方的设置。
      </div>
      <template #footer>
        <el-button @click="wordModalVisible = false">取消</el-button>
        <el-button type="primary" :loading="exportingWord" @click="confirmExportWord">导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getGlobalPreview,
  calculateRatios,
  updateRatios,
  exportGlobalPreview,
  exportWordReportDownload,
} from '@/api/backtestMulti'
import { exportReturnSeries } from '@/composables/useReturnSeriesExport'
import { pickPagingQuery } from '@/utils/pageState'
import PageToolbar from '@/components/PageToolbar.vue'

const route = useRoute()
const taskId = route.params.id
const pagingQuery = pickPagingQuery(route.query)

const loading = ref(false)
const calculating = ref(false)
const savingRatios = ref(false)
const exportingWord = ref(false)

const taskName = ref('')
const summary = ref({})
const groups = ref([])
const activeGroupKey = ref('')
const products = ref([])
// 页面正在编辑的比例值（数值数组，下标即 product_index）
const ratioValues = ref([])
// ===== 无风险利率（页面唯一入口，单位：百分比，如 3 = 3%）=====
// 口径：影响后端按当前比例实时重算的指标（比例后列、比例计算列）与导出报告
// （Excel / Word）；单品「指数 / 模型结果」列是回测执行结果，不参与重算。
// 页面填百分比，请求统一转小数（0.03）——与 runtime_params.risk_free_rate 一致。
const riskFreePercent = ref(0)

let hasUnsavedRatioPreview = false
let appliedRatioSignature = ''

// 严格读取：非法输入抛错，交由调用方提示（计算预览 / 保存比例 / 导出前调用）。
function readRiskFreePercent() {
  const raw = riskFreePercent.value
  if (raw === null || raw === undefined || raw === '') {
    return 0
  }
  const percent = Number(raw)
  if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
    throw new Error('无风险利率需为 0～100 之间的数字（百分比）')
  }
  return percent
}

// 宽松读取：脏标记计算用，非法输入返回 NaN 以便与已应用值判为不同。
function riskFreePercentForSignature() {
  const raw = riskFreePercent.value
  return raw === null || raw === undefined || raw === '' ? 0 : Number(raw)
}

// 0 值不带参数：默认口径下请求 URL 与历史行为逐字一致。非法输入抛错（同严格读取）。
function riskFreeQueryParams() {
  const percent = readRiskFreePercent()
  return percent === 0 ? undefined : { risk_free_rate: percent / 100 }
}

// 回填输入框：以后端回显的口径为准，保证「显示值 = 计算值」。
function applyRiskFreeFromPayload(res) {
  const decimal = Number(res?.runtime_params?.risk_free_rate)
  if (!Number.isFinite(decimal)) {
    return
  }
  riskFreePercent.value = Number((decimal * 100).toFixed(6))
}

const activeGroup = computed(() => groups.value.find((g) => g.group_key === activeGroupKey.value) || null)

// 比例为 0 的产品不参与组合，全 0 列没有展示意义，直接不渲染其列组。
const visibleProducts = computed(() =>
  products.value
    .map((product, index) => ({ product, index }))
    .filter((item) => Number(item.product.ratio || 0) > 0)
)

const ratioRows = computed(() =>
  products.value.map((product, index) => ({
    index,
    label: product.product_name || product.stock_code || `产品 ${index + 1}`,
    stockMarket: `${product.stock_code || '-'} / ${product.market_type || '-'}`,
    ratio: ratioValues.value[index] ?? Number(product.ratio || 0),
  }))
)

const ratioTotalValue = computed(() =>
  ratioValues.value.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0)
)

const ratioInputsDirty = computed(() => currentInputSignature() !== appliedRatioSignature)

const ratioStatusText = computed(() => {
  const total = Number(ratioTotalValue.value.toFixed(4))
  const suffix = ratioInputsDirty.value ? '（需计算预览）' : hasUnsavedRatioPreview ? '（未保存）' : ''
  return `合计 ${total}%${suffix}`
})

const headDescription = computed(() => {
  const task = summary.value
  if (!task || !task.start_date) return taskName.value || '加载中...'
  return `${taskName.value} · ${task.start_date} ~ ${task.end_date || '-'}`
})

const emptyText = computed(() => {
  if (loading.value) return '正在加载全局预览数据...'
  if (!groups.value.length) return '当前没有可展示的参数方案'
  if (!visibleProducts.value.length) return '所有产品比例均为 0，没有可展示的产品'
  return '该分组下没有成功结果'
})

function normalizeRatioForSignature(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? String(Number(number.toFixed(8))) : 'NaN'
}

function ratioSignatureFromValues(values) {
  return (values || []).map(normalizeRatioForSignature).join('|')
}

// 「比例 + 无风险利率」联合签名：任一变化都要求重新计算预览。
function inputSignature(values, riskFreePercentValue) {
  return `${ratioSignatureFromValues(values)}|rf=${normalizeRatioForSignature(riskFreePercentValue)}`
}

function currentInputSignature() {
  return inputSignature(ratioValues.value, riskFreePercentForSignature())
}

function payloadInputSignature(res) {
  const decimal = Number(res?.runtime_params?.risk_free_rate || 0)
  return inputSignature(
    (res?.products || []).map((product) => product.ratio),
    decimal * 100,
  )
}

function formatRatioHeader(value) {
  const text = String(value == null ? '' : value).trim()
  if (!text) return '-'
  return text.endsWith('%') ? text : `${text}%`
}

function cellValue(row, productIndex, key) {
  const item = (row.product_values || [])[productIndex] || {}
  return item[key] || '-'
}

function syncRatioValuesFromProducts() {
  ratioValues.value = products.value.map((product) => Number(product.ratio || 0))
}

function updateRatio(index, value) {
  ratioValues.value[index] = Number.isFinite(Number(value)) ? Number(value) : 0
}

// 支持从权重组合分析页"查看"跳转：URL 携带 ratios=[{stock_code, ratio}]，
// 按 stock_code 匹配产品改写比例（组合外产品归 0）。必须在首次渲染前调用。
function takeRatiosFromUrlQuery() {
  const raw = route.query.ratios
  if (!raw || typeof raw !== 'string') return false
  let entries = []
  try {
    entries = JSON.parse(raw)
  } catch (error) {
    console.warn('ratios 参数解析失败', error)
    return false
  }
  if (!Array.isArray(entries) || !entries.length) return false
  const ratioByCode = new Map(
    entries
      .filter((item) => item && item.stock_code != null)
      .map((item) => [String(item.stock_code), Number(item.ratio) || 0]),
  )
  if (!ratioByCode.size) return false
  const matched = products.value.some((product) => ratioByCode.has(String(product.stock_code || '')))
  if (!matched) {
    console.warn('ratios 参数未匹配到任何产品，忽略')
    return false
  }
  products.value.forEach((product) => {
    const ratio = ratioByCode.get(String(product.stock_code || ''))
    product.ratio = ratio === undefined ? 0 : ratio
  })
  syncRatioValuesFromProducts()
  // 用完即清，避免刷新后再次覆盖用户手动输入
  const query = { ...route.query }
  delete query.ratios
  window.history.replaceState({}, '', route.path + (Object.keys(query).length ? `?${new URLSearchParams(query)}` : ''))
  return true
}

function collectRatioPayload() {
  return ratioValues.value.map((ratio, index) => ({ product_index: index, ratio }))
}

async function applyRatioPreview() {
  if (ratioValues.value.some((value) => !Number.isFinite(value) || value < 0)) {
    ElMessage.warning('产品比例必须是大于等于 0 的数字')
    return
  }
  let runtimeParams
  try {
    runtimeParams = { risk_free_rate: readRiskFreePercent() / 100 }
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }
  const signature = currentInputSignature()
  if (signature === appliedRatioSignature) {
    ElMessage.info('比例与无风险利率均未变化，无需重新计算')
    return
  }

  calculating.value = true
  try {
    const res = await calculateRatios(taskId, {
      ratios: ratioValues.value.map((ratio, index) => ({ product_index: index, ratio })),
      runtime_params: runtimeParams,
    })
    applyPayload(res)
    hasUnsavedRatioPreview = true
  } catch (error) {
    ElMessage.error(error.message || '计算失败')
  } finally {
    calculating.value = false
  }
}

function applyPayload(res) {
  summary.value = res.summary || {}
  taskName.value = res.task?.name || taskId
  groups.value = res.groups || []
  products.value = res.products || []
  if (groups.value.length && !groups.value.some((g) => g.group_key === activeGroupKey.value)) {
    activeGroupKey.value = groups.value[0].group_key
  }
  // 回填后端回显口径，保证「显示值 = 计算值」。
  applyRiskFreeFromPayload(res)
  syncRatioValuesFromProducts()
  appliedRatioSignature = payloadInputSignature(res)
}

async function saveRatios() {
  if (ratioInputsDirty.value) {
    ElMessage.warning('比例或无风险利率已修改，请先点击"计算预览"确认结果，再保存比例。')
    return
  }
  if (ratioValues.value.some((value) => !Number.isFinite(value) || value < 0)) {
    ElMessage.warning('产品比例必须是大于等于 0 的数字')
    return
  }
  let runtimeParams
  try {
    runtimeParams = { risk_free_rate: readRiskFreePercent() / 100 }
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }
  savingRatios.value = true
  try {
    const res = await updateRatios(taskId, { ratios: collectRatioPayload(), runtime_params: runtimeParams })
    applyPayload(res)
    hasUnsavedRatioPreview = false
    ElMessage.success('比例保存成功')
  } catch (error) {
    ElMessage.error(error.message || '保存比例失败')
  } finally {
    savingRatios.value = false
  }
}

function onGroupChange() {}

function buildExcelDownloadName() {
  const safeName = String(taskName.value || taskId)
    .trim()
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/[ .]+$/g, '')
  return `${safeName || taskId}.xlsx`
}

async function exportXlsx() {
  let riskFreeParams
  try {
    // 无风险利率与比例同为页面口径：导出必须带上，否则 Excel 里的夏普/索提诺
    // 会退回默认口径，与页面看到的不一致。
    const percent = readRiskFreePercent()
    riskFreeParams = percent === 0 ? undefined : { risk_free_rate: percent / 100 }
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }
  try {
    // 比例已计算但未保存时，携带预览比例导出（与静态版一致）
    const params = {
      ...(hasUnsavedRatioPreview && !ratioInputsDirty.value
        ? { ratios: JSON.stringify(collectRatioPayload()) }
        : {}),
      ...riskFreeParams,
    }
    const blob = await exportGlobalPreview(taskId, Object.keys(params).length ? params : undefined)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = buildExcelDownloadName()
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  }
}

async function exportSeries() {
  if (!activeGroupKey.value) {
    ElMessage.warning('当前没有可导出的参数方案')
    return
  }
  try {
    // 组合公式按当前页面比例写权重；不传时后端用任务默认比例。
    await exportReturnSeries({
      taskId,
      taskName: taskName.value || taskId,
      groupKey: activeGroupKey.value,
      ratios: collectRatioPayload(),
    })
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  }
}

// ===== 导出 Word 选股弹窗（多选+比例；组合指数是否并列由开关控制，默认开启） =====
// 语义 A：每个基准条目 = {code, ratio}，基准序列按 比例×指数日收益+现金 缩放；
// 同一产品可用不同比例添加多条（如 QQQ 50% 与 QQQ 100% 两条基准列）。
const DEFAULT_BENCHMARK_RATIO = 100

// 组合指数开关：默认开启；开启时全部产品按比例组合为一个基准列，列头固定"指数"。
const includeCompositeBenchmark = ref(true)

// 价格类型取值 → 报告"价格类型"展示行文案（与后端 get_price_type 一致）。
const EXPORT_WORD_PRICE_TYPE_LABELS = {
  kp_price: '开盘价',
  sp_price: '收盘价',
  vwap_price: '加权平均价',
  ohlc_price: 'OHLC（开高低收）',
  random_price: '随机价',
}

const wordModalVisible = ref(false)
const stockSearch = ref('')
const benchmarkEntries = ref([])
const wordPriceType = ref('')
const wordRiskFreePercent = ref(0)

const stockOptions = computed(() => {
  const keyword = stockSearch.value.trim().toLowerCase()
  return products.value
    .map((product, index) => ({
      index,
      name: product.product_name || `产品${index + 1}`,
      code: product.stock_code || '',
      ratio: Number(product.ratio || 0),
    }))
    .filter((item) => item.code)
    .filter((item) => !keyword || item.name.toLowerCase().includes(keyword) || item.code.toLowerCase().includes(keyword))
})

function stockEntryCount(code) {
  return benchmarkEntries.value.filter((entry) => entry.code === code).length
}

function addBenchmark(code) {
  benchmarkEntries.value.push({ code, ratio: DEFAULT_BENCHMARK_RATIO })
}

function removeBenchmark(index) {
  benchmarkEntries.value.splice(index, 1)
}

// 比例语义为 (0, 100]，非法输入回退默认 100；后端 Schema 兜底校验。
function updateBenchmarkRatio(entry, value) {
  const number = Number(value)
  entry.ratio = Number.isFinite(number) && number > 0 ? Math.min(number, 100) : DEFAULT_BENCHMARK_RATIO
}

// 读取弹窗配置：无风险利率按百分比填写（如 3 = 3%），payload 统一转小数
// （0.03）双通道（metadata 展示 + runtime_params 重算）；价格类型仅展示，
// 留空表示跟随任务配置。非法输入抛错交由调用方提示。
function readExportWordOptions() {
  const raw = wordRiskFreePercent.value
  let percent = 0
  if (raw !== null && raw !== undefined && raw !== '') {
    percent = Number(raw)
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
      throw new Error('无风险利率需为 0～100 之间的数字（百分比）')
    }
  }
  const priceValue = wordPriceType.value || ''
  return {
    metadata: {
      ...(priceValue ? { price_type: EXPORT_WORD_PRICE_TYPE_LABELS[priceValue] } : {}),
      risk_free_rate: `${percent.toFixed(2)}%`,
    },
    runtime_params: { risk_free_rate: percent / 100 },
  }
}

function openExportWordModal() {
  if (ratioInputsDirty.value) {
    ElMessage.warning('比例或无风险利率已修改，请先点击"计算预览"确认结果，再导出 Word。')
    return
  }
  if (!activeGroupKey.value) {
    ElMessage.warning('当前没有可导出的参数方案')
    return
  }
  // 页面上的无风险利率是默认口径：打开弹窗时同步当前值，仍可在弹窗内临时覆盖
  // （覆盖只影响本次导出，不回写页面）。
  const currentPercent = riskFreePercentForSignature()
  wordRiskFreePercent.value = Number.isFinite(currentPercent) ? currentPercent : 0
  stockSearch.value = ''
  benchmarkEntries.value = []
  wordModalVisible.value = true
}

async function confirmExportWord() {
  exportingWord.value = true
  try {
    const payload = {
      report_type: 'RPT-M',
      task_id: taskId,
      group_key: activeGroupKey.value,
      ratios: collectRatioPayload(),
      include_composite_benchmark: includeCompositeBenchmark.value,
    }
    const benchmarks = benchmarkEntries.value.map((entry) => ({
      stock_code: entry.code,
      ratio: Number(entry.ratio) || DEFAULT_BENCHMARK_RATIO,
    }))
    if (benchmarks.length) {
      // 弹窗选出的基准数组整体赋给 index_benchmarks（支持同股不同比例多条）。
      payload.index_benchmarks = benchmarks
    }
    // 弹窗配置随请求透传：后端把请求 metadata/runtime_params 覆盖到按
    // 任务重建的载荷上（价格类型展示行 + 无风险利率重算）。
    Object.assign(payload, readExportWordOptions())

    // 文件名优先取响应 Content-Disposition，回退 RPT-M_{code+比例后缀...|all}.docx（静态版同口径）
    const fallbackFilename = `RPT-M_${
      benchmarks.map((item) => `${item.stock_code}${item.ratio === 100 ? '' : item.ratio}`).join('_') || 'all'
    }.docx`
    const { blob, filename } = await exportWordReportDownload(payload, fallbackFilename)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    wordModalVisible.value = false
  } catch (error) {
    ElMessage.error(error.message || 'Word 导出失败')
  } finally {
    exportingWord.value = false
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await getGlobalPreview(taskId, riskFreeQueryParams())
    summary.value = { ...(res.summary || {}), ...(res.task || {}) }
    taskName.value = res.task?.name || taskId
    groups.value = res.groups || []
    products.value = res.products || []
    activeGroupKey.value = groups.value.length ? groups.value[0].group_key : ''
    // 回填后端回显的无风险利率，再以「比例 + 无风险利率」联合口径记录已应用签名
    applyRiskFreeFromPayload(res)
    appliedRatioSignature = payloadInputSignature(res)
    hasUnsavedRatioPreview = false
    syncRatioValuesFromProducts()

    // 在首次渲染前应用跳转携带的比例，避免先展示原比例再跳变
    const ratiosApplied = takeRatiosFromUrlQuery()
    if (ratiosApplied && ratioInputsDirty.value) {
      // 携带的比例与已保存不同：先按新比例算完再展示
      loading.value = true
      await applyRatioPreview()
    }
  } catch (error) {
    ElMessage.error(error.message || '加载全局预览失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.backtest-multi-preview-page__ratio-input {
  width: 140px;
}

.full-width {
  width: 100%;
}

.backtest-multi-preview-page__metrics {
  margin-bottom: 4px;
}

.backtest-multi-preview-page__metric-id {
  margin-top: 6px;
  word-break: break-all;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-preview-page__metric-value {
  margin-top: 6px;
  color: var(--app-text);
  font-size: 22px;
  font-weight: 700;
}

.backtest-multi-preview-page__metric-value--success {
  color: #16a34a;
}

.backtest-multi-preview-page__layout {
  display: grid;
  gap: 0;
}

.backtest-multi-preview-page__empty {
  padding: 64px 0;
}

.backtest-multi-preview-page__table-wrap {
  overflow: auto;
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
}

.backtest-multi-preview-page__table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
}

.backtest-multi-preview-page__table th,
.backtest-multi-preview-page__table td {
  padding: 8px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  vertical-align: middle;
  text-align: center;
  font-size: 12px;
}

.backtest-multi-preview-page__table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgba(232, 239, 250, 0.82);
}

.backtest-multi-preview-page__product-row td {
  font-weight: 700;
  color: var(--app-text);
  background: rgba(232, 239, 250, 0.82);
}

.sticky-col {
  position: sticky;
  z-index: 1;
  background: rgba(255, 255, 255, 0.98);
}

.sticky-col-1 {
  left: 0;
  min-width: 120px;
  background: #f7e1a1;
}

.sticky-col-2 {
  left: 120px;
  min-width: 180px;
}

.backtest-multi-preview-page__table thead .sticky-col {
  z-index: 3;
  background: rgba(232, 239, 250, 0.96);
}

.backtest-multi-preview-page__table thead .sticky-col-1 {
  background: #f7e1a1;
}

.backtest-multi-preview-page__sticky-main {
  color: var(--app-text);
  font-weight: 700;
}

.backtest-multi-preview-page__ratio-formula-hint {
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--app-text-muted, #64748b);
}

.backtest-multi-preview-page__hint-title {
  color: var(--app-text);
  font-weight: 700;
}

.backtest-multi-preview-page__hint-note {
  color: #94a3b8;
}

.backtest-multi-preview-page__word-search {
  margin-bottom: 12px;
}

.backtest-multi-preview-page__stock-list {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  max-height: 320px;
  overflow: auto;
}

.backtest-multi-preview-page__word-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.backtest-multi-preview-page__benchmark-list {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.backtest-multi-preview-page__benchmark-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backtest-multi-preview-page__benchmark-code {
  flex: 1;
  min-width: 0;
  color: var(--app-text);
  font-weight: 600;
}

.backtest-multi-preview-page__stock-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
}

.backtest-multi-preview-page__stock-row:last-child {
  border-bottom: none;
}
</style>
