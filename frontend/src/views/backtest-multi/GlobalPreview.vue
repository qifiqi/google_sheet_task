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
          <el-table-column label="比例(%)" width="220">
            <template #default="{ row }">
              <el-input-number
                :model-value="ratioValues[row.index]"
                :min="0"
                :step="0.0001"
                :controls="false"
                size="small"
                style="width: 140px"
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

    <!-- Word 导出选股弹窗 -->
    <el-dialog v-model="wordModalVisible" title="导出 Word 报告" width="420px">
      <el-input
        v-model="stockSearch"
        placeholder="搜索股票名称 / 代码"
        clearable
        class="backtest-multi-preview-page__word-search"
      />
      <el-radio-group v-model="selectedStockCode" class="backtest-multi-preview-page__stock-list">
        <el-radio value="">
          <span class="panel-note">不指定默认使用组合index</span>
        </el-radio>
        <el-radio v-for="item in stockOptions" :key="item.code" :value="item.code">
          <span>{{ item.name }} ({{ item.code }})</span>
          <small class="panel-note">比例 {{ item.ratio }}%</small>
        </el-radio>
        <div v-if="!stockOptions.length" class="panel-note">没有匹配的股票</div>
      </el-radio-group>
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

let hasUnsavedRatioPreview = false
let appliedRatioSignature = ''

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
    ratio: ratioValues.value[index] ?? Number(product.ratio || 0),
  }))
)

const ratioTotalValue = computed(() =>
  ratioValues.value.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0)
)

const ratioInputsDirty = computed(() => ratioSignatureFromValues(ratioValues.value) !== appliedRatioSignature)

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

function ratioSignatureFromProducts(list) {
  return ratioSignatureFromValues((list || []).map((product) => Number(product.ratio || 0)))
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
  const signature = ratioSignatureFromValues(ratioValues.value)
  if (signature === appliedRatioSignature) {
    hasUnsavedRatioPreview = false
    ElMessage.info('比例未变化，无需重新计算')
    return
  }

  calculating.value = true
  try {
    const res = await calculateRatios(taskId, {
      ratios: ratioValues.value.map((ratio, index) => ({ product_index: index, ratio })),
    })
    applyPayload(res)
    hasUnsavedRatioPreview = true
    appliedRatioSignature = signature
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
  syncRatioValuesFromProducts()
}

async function saveRatios() {
  if (ratioInputsDirty.value) {
    ElMessage.warning('比例已修改，请先点击"计算预览"确认结果，再保存比例。')
    return
  }
  if (ratioValues.value.some((value) => !Number.isFinite(value) || value < 0)) {
    ElMessage.warning('产品比例必须是大于等于 0 的数字')
    return
  }
  savingRatios.value = true
  try {
    const res = await updateRatios(taskId, { ratios: collectRatioPayload() })
    applyPayload(res)
    hasUnsavedRatioPreview = false
    appliedRatioSignature = ratioSignatureFromProducts(products.value)
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
  try {
    // 比例已计算但未保存时，携带预览比例导出（与静态版一致）
    const params = hasUnsavedRatioPreview && !ratioInputsDirty.value
      ? { ratios: JSON.stringify(collectRatioPayload()) }
      : undefined
    const blob = await exportGlobalPreview(taskId, params)
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

// ===== 导出 Word 选股弹窗（单选，可为空） =====
const wordModalVisible = ref(false)
const stockSearch = ref('')
const selectedStockCode = ref('')

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

function openExportWordModal() {
  if (ratioInputsDirty.value) {
    ElMessage.warning('比例已修改，请先点击"计算预览"确认结果，再导出 Word。')
    return
  }
  if (!activeGroupKey.value) {
    ElMessage.warning('当前没有可导出的参数方案')
    return
  }
  selectedStockCode.value = ''
  stockSearch.value = ''
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
    }
    if (selectedStockCode.value) {
      payload.index_stock_code = selectedStockCode.value
    }
    // 文件名优先取响应 Content-Disposition，回退 RPT-M_{code|all}.docx（静态版同口径）
    const { blob, filename } = await exportWordReportDownload(payload, `RPT-M_${selectedStockCode.value || 'all'}.docx`)
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
    const res = await getGlobalPreview(taskId)
    summary.value = { ...(res.summary || {}), ...(res.task || {}) }
    taskName.value = res.task?.name || taskId
    groups.value = res.groups || []
    products.value = res.products || []
    activeGroupKey.value = groups.value.length ? groups.value[0].group_key : ''
    appliedRatioSignature = ratioSignatureFromProducts(products.value)
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
</style>
