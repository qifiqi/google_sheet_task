<template>
  <div class="app-page weight-combination-page">
    <PageToolbar
      eyebrow="绩效分析"
      title="权重组合分析"
      description="按步长穷举组合权重，流式接收每个组合的年化收益、最大回撤指标。"
    >
      <template #actions>
        <el-button class="page-back-button" @click="$router.push('/performance_analysis')">返回</el-button>
      </template>
    </PageToolbar>

    <el-card shadow="never" class="weight-combination-page__section">
      <template #header><span>参数配置</span></template>
      <el-form :model="form" inline label-position="top" @submit.prevent="handleAnalyze">
        <el-form-item label="任务 ID" required>
          <el-input v-model="form.taskId" placeholder="输入任务 ID" class="weight-combination-page__task-id-input" @change="onTaskIdChange" />
        </el-form-item>
        <el-form-item label="步长(%)">
          <el-input-number v-model="form.step" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="上限(%)">
          <el-input-number v-model="form.maxWeight" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="下限(%)">
          <el-input-number v-model="form.minWeight" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="单股上限(%)">
          <el-input-number v-model="form.singleCap" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="analyzing" @click="handleAnalyze">开始分析</el-button>
          <el-button v-if="analyzing" type="danger" @click="handleCancel">取消</el-button>
        </el-form-item>
      </el-form>

      <!-- 产品选择 + 单股范围：任务 ID 失焦自动加载，勾选/范围按 result_id 回传
           （老 weight_combination_tabulator.js 产品面板的等价迁移） -->
      <div v-if="productsPanelVisible" class="weight-combination-page__products">
        <div class="weight-combination-page__products-toolbar">
          <span>{{ productsSummary }}</span>
          <div>
            <el-button
              size="small"
              :disabled="productsLoading || analyzing"
              title="按任务配置的比例重新生成 0 ~ 比例 的默认范围"
              @click="resetProductRanges"
            >重置范围</el-button>
            <el-button size="small" :loading="productsLoading" :disabled="analyzing" @click="reloadProducts">重新加载</el-button>
          </div>
        </div>
        <div class="helper-text weight-combination-page__products-hint">
          勾选本次参与组合的产品，并设置单股权重范围（默认 0 ~ 任务配置比例，按步长
          {{ readStep() }}% 向下取整；配置比例为 0 的产品默认不勾选）；
          范围须为步长整数倍，启用单股范围后上方「单股上限」不再生效。
        </div>
        <el-alert v-if="productsError" :title="productsError" type="error" :closable="false" />
        <el-table
          v-else
          ref="productsTableRef"
          v-loading="productsLoading"
          element-loading-text="正在加载产品列表..."
          :data="products"
          size="small"
          max-height="320"
          :row-class-name="productRowClass"
          @selection-change="onProductsSelectionChange"
        >
          <el-table-column type="selection" width="46" :selectable="isProductSelectable" align="center" />
          <el-table-column label="产品名称" min-width="180">
            <template #default="{ row }">
              <span :title="row.usable ? undefined : '该产品没有可用的收益序列，无法参与组合'">
                {{ row.stock_name || row.stock_code || 'N/A' }}
              </span>
              <div class="helper-text">{{ row.stock_code }}</div>
            </template>
          </el-table-column>
          <el-table-column label="配置比例" width="110" align="right">
            <template #default="{ row }">{{ formatRatioText(row.ratioNum) }}</template>
          </el-table-column>
          <el-table-column label="单股下限(%)" width="160">
            <template #default="{ row }">
              <el-input-number
                v-model="row.min"
                :min="0"
                :max="100"
                :step="1"
                size="small"
                :disabled="analyzing || !row.usable || !row.checked"
              />
            </template>
          </el-table-column>
          <el-table-column label="单股上限(%)" width="160">
            <template #default="{ row }">
              <el-input-number
                v-model="row.max"
                :min="0"
                :max="100"
                :step="1"
                size="small"
                :disabled="analyzing || !row.usable || !row.checked"
              />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card v-if="analyzing || progressVisible" shadow="never" class="weight-combination-page__section">
      <template #header><span>分析进度</span></template>
      <el-progress
        :percentage="progressPercent >= 0 ? progressPercent : 100"
        :indeterminate="progressPercent < 0"
        :stroke-width="16"
      />
      <div class="weight-combination-page__progress-info">{{ progressInfo }}</div>
    </el-card>

    <el-card v-if="rows.length" shadow="never">
      <template #header>
        <div class="weight-combination-page__results-head">
          <div>
            <span>组合分析结果</span>
            <el-tag type="success" size="small" class="weight-combination-page__stat">{{ filteredRows.length }} 条显示</el-tag>
            <el-tag type="primary" size="small" class="weight-combination-page__stat">{{ rows.length }} 条总计</el-tag>
          </div>
          <div>
            <el-button size="small" type="success" @click="exportCsv">导出 CSV</el-button>
            <el-button size="small" @click="clearFilters">清除筛选</el-button>
          </div>
        </div>
      </template>

      <el-table :data="filteredRows" height="600" border>
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column
          label="股票组合"
          prop="stocks_display"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column
          v-for="col in numericColumns"
          :key="col.prop"
          :prop="col.prop"
          :width="col.width"
          align="right"
          sortable
        >
          <template #header>
            <el-popover placement="bottom-end" :width="220" trigger="click" @show="seedDraft(col.prop)">
              <template #reference>
                <span class="weight-combination-page__col-head" @click.stop>
                  {{ col.label }}
                  <el-icon class="weight-combination-page__funnel" :class="{ 'is-active': hasActiveFilter(col.prop) }">
                    <Filter />
                  </el-icon>
                </span>
              </template>
              <div class="weight-combination-page__filter">
                <el-input v-model="filterDrafts[col.prop].min" type="number" placeholder="最小值（不限）" size="small" />
                <el-input v-model="filterDrafts[col.prop].max" type="number" placeholder="最大值（不限）" size="small" />
                <div v-if="filterDrafts[col.prop].invalid" class="weight-combination-page__filter-hint">最小值不能大于最大值</div>
                <div class="weight-combination-page__filter-actions">
                  <el-button size="small" @click="clearRangeFilter(col.prop)">清除</el-button>
                  <el-button size="small" type="primary" @click="applyRangeFilter(col.prop)">应用</el-button>
                </div>
              </div>
            </el-popover>
          </template>
          <template #default="{ row }">
            {{ formatNumber(row[col.prop], col.digits, col.suffix) }}
          </template>
        </el-table-column>
        <el-table-column label="查看" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openGlobalPreviewWithRatios(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Filter } from '@element-plus/icons-vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { analyzeWeightCombinationStream, getWeightCombinationProducts } from '@/api/performance_analysis'

const route = useRoute()
const router = useRouter()

const form = reactive({
  taskId: '',
  step: 5,
  maxWeight: 100,
  minWeight: 50,
  singleCap: 30,
})

const analyzing = ref(false)
const progressVisible = ref(false)
const progressPercent = ref(0)
const progressInfo = ref('准备中...')
let abortController = null

// ── 产品选择 + 单股范围（老 weight_combination_tabulator.js 产品面板等价迁移）──
// 每项对应一个 TaskResult。多参数方案任务里同一股票会出现多次，
// 提交时按 result_id 回传，服务端据此精确对应到枚举中的产品。
const products = ref([])
const productsTableRef = ref(null)
const productsPanelVisible = ref(false)
const productsLoading = ref(false)
const productsError = ref('')
let productsTaskId = ''   // 已成功加载面板的任务 ID（用于跳过重复请求）
let productsLoadSeq = 0   // 请求序号：旧响应回来时直接丢弃
let productsAbort = null  // 切换任务时中止上一次加载

// 结果行（已 transform）；流式接收时先攒 batch 再落 ref，避免每行触发整表重渲染
const rows = ref([])
let pendingRows = []

const numericColumns = [
  { prop: 'index_rate_disp', label: '年化收益率(指数)', width: 185, digits: 2, suffix: '%' },
  { prop: 'start_rate_disp', label: '年化收益率(策略)', width: 185, digits: 2, suffix: '%' },
  { prop: 'index_dd_disp', label: '最大回撤(指数)', width: 175, digits: 2, suffix: '%' },
  { prop: 'start_dd_disp', label: '最大回撤(策略)', width: 175, digits: 2, suffix: '%' },
  { prop: 'weight_sum', label: '权重和(%)', width: 140, digits: 0, suffix: '%' },
]

// 已生效的范围筛选：prop -> { min: number|null, max: number|null }
const rangeFilters = reactive({})
// 弹窗内草稿：prop -> { min, max, invalid }
const filterDrafts = reactive({})

numericColumns.forEach((col) => {
  rangeFilters[col.prop] = { min: null, max: null }
  filterDrafts[col.prop] = { min: '', max: '', invalid: false }
})

function hasActiveFilter(prop) {
  const f = rangeFilters[prop]
  return !!(f && (f.min !== null || f.max !== null))
}

function seedDraft(prop) {
  const f = rangeFilters[prop]
  filterDrafts[prop].min = f.min !== null ? String(f.min) : ''
  filterDrafts[prop].max = f.max !== null ? String(f.max) : ''
  filterDrafts[prop].invalid = false
}

function applyRangeFilter(prop) {
  const draft = filterDrafts[prop]
  const min = draft.min === '' ? null : parseFloat(draft.min)
  const max = draft.max === '' ? null : parseFloat(draft.max)
  if (min !== null && max !== null && min > max) {
    draft.invalid = true
    return
  }
  rangeFilters[prop] = { min, max }
  draft.invalid = false
}

function clearRangeFilter(prop) {
  rangeFilters[prop] = { min: null, max: null }
  filterDrafts[prop].min = ''
  filterDrafts[prop].max = ''
  filterDrafts[prop].invalid = false
}

function clearFilters() {
  numericColumns.forEach((col) => {
    rangeFilters[col.prop] = { min: null, max: null }
  })
}

const filteredRows = computed(() =>
  rows.value.filter((row) =>
    numericColumns.every((col) => {
      const f = rangeFilters[col.prop]
      if (f.min === null && f.max === null) return true
      // 空值/非数值放行（与静态版 minMaxFilterFunction 一致）
      const raw = row[col.prop]
      if (raw === null || raw === undefined || raw === '') return true
      const value = parseFloat(raw)
      if (Number.isNaN(value)) return true
      if (f.min !== null && value < f.min) return false
      if (f.max !== null && value > f.max) return false
      return true
    })
  )
)

function formatNumber(value, digits, suffix) {
  if (value === null || value === undefined || value === '') return '-'
  return `${Number(value).toFixed(digits)}${suffix}`
}

// ============ 产品选择 + 单股范围 ============
function productLabel(product) {
  return product.stock_name || product.stock_code || '结果 ' + product.result_id
}

function isRequestCanceled(error) {
  return error?.name === 'AbortError'
    || error?.name === 'CanceledError'
    || error?.code === 'ERR_CANCELED'
    || error?.cause?.name === 'CanceledError'
    || error?.cause?.code === 'ERR_CANCELED'
}

function parseRatioText(raw) {
  if (raw === null || raw === undefined || raw === '') return null
  const value = parseFloat(raw)
  return Number.isFinite(value) ? value : null
}

function formatRatioText(value) {
  if (value === null || value === undefined) return '-'
  return (Math.round(value * 100) / 100) + '%'
}

function readStep() {
  const step = Number(form.step)
  return Number.isInteger(step) && step > 0 ? step : 5
}

// 默认单股上限 = 任务配置比例（无配置比例时回退「单股上限」输入框），
// 按步长向下取整：既保证"0 ~ 配置比例"的语义，也不会因取整超过配置比例。
function defaultMaxRatio(product, step) {
  let base = product.ratioNum
  if (base === null || base === undefined) {
    const fallback = Number(form.singleCap)
    base = Number.isInteger(fallback) ? fallback : 100
  }
  const capped = Math.max(0, Math.min(base, 100))
  return Math.floor(capped / step) * step
}

function resetProductRanges() {
  const step = readStep()
  products.value.forEach((product) => {
    product.min = 0
    product.max = defaultMaxRatio(product, step)
  })
}

const productsSummary = computed(() => {
  const usable = products.value.filter((product) => product.usable)
  const selected = usable.filter((product) => product.checked)
  if (!usable.length) {
    return products.value.length ? '没有可用于组合的产品' : '暂无产品'
  }
  const ratioSum = selected.reduce((sum, product) => sum + (product.ratioNum || 0), 0)
  return `已选 ${selected.length} / 共 ${usable.length}` +
    (ratioSum > 0 ? `（所选配置比例合计 ${formatRatioText(ratioSum)}）` : '')
})

// 不可用或未勾选的行置灰（与老版 wc-products__row--off 一致）
function productRowClass({ row }) {
  return row.usable && row.checked ? '' : 'weight-combination-page__product-row--off'
}

function isProductSelectable(row) {
  return row.usable
}

function onProductsSelectionChange(selectedRows) {
  // 勾选态同步回行数据：摘要、置灰与提交载荷都读 row.checked
  products.value.forEach((product) => {
    product.checked = selectedRows.includes(product)
  })
}

function onTaskIdChange() {
  // 任务 ID 失焦/回车后加载产品列表；同一任务已加载过则不重复请求
  loadProducts(form.taskId.trim())
}

function reloadProducts() {
  loadProducts(form.taskId.trim(), { force: true })
}

async function loadProducts(taskId, { force = false } = {}) {
  if (!force && taskId && taskId === productsTaskId) return
  productsTaskId = ''
  if (productsAbort) {
    productsAbort.abort()
    productsAbort = null
  }
  if (!taskId) {
    products.value = []
    productsPanelVisible.value = false
    productsError.value = ''
    productsLoading.value = false
    return
  }

  const seq = ++productsLoadSeq
  productsAbort = new AbortController()
  // 任务 ID 变更由输入框失焦（change）触发，紧接着的提交仍会读到上一个任务的
  // products；标记加载中，让 handleAnalyze 拒绝这次提交而不是发错范围。
  productsLoading.value = true
  productsPanelVisible.value = true
  productsError.value = ''

  try {
    const data = await getWeightCombinationProducts(taskId, { signal: productsAbort.signal })
    if (seq !== productsLoadSeq) return

    const list = data?.products || []
    products.value = list.map((item) => {
      const ratioNum = parseRatioText(item.ratio)
      return {
        result_id: item.result_id,
        product_index: item.product_index,
        stock_code: item.stock_code,
        stock_name: item.stock_name,
        ratioNum,
        usable: !!item.has_returns,
        // 已配置比例为 0 的产品在组合里本就不参与，默认不勾选（可手动勾选后改上限）
        checked: !!item.has_returns && ratioNum !== 0,
        min: 0,
        max: 0,
      }
    })
    resetProductRanges()
    productsTaskId = taskId

    if (!products.value.length) {
      productsError.value = '该任务没有成功的结果，无法进行权重组合分析。'
    } else if (!products.value.some((product) => product.usable)) {
      productsError.value = '该任务的成功结果都没有可用的收益序列，无法进行权重组合分析。'
    }

    // el-table 数据替换后选择会被清空，按默认勾选重建；全选/半选态由表头复选框自带
    await nextTick()
    if (seq !== productsLoadSeq) return
    products.value.forEach((row) => {
      if (row.checked) productsTableRef.value?.toggleRowSelection(row, true)
    })
  } catch (error) {
    if (isRequestCanceled(error)) return
    if (seq !== productsLoadSeq) return
    products.value = []
    productsError.value = '产品列表加载失败：' + (error?.message || '未知错误')
  } finally {
    if (seq === productsLoadSeq) {
      productsAbort = null
      productsLoading.value = false
    }
  }
}

// 校验面板选择并生成请求字段；面板未加载（无产品）时返回空载荷，
// 请求退化为原有的"全部产品 + 全局单股上限"语义。
function collectProductSelection() {
  if (!products.value.length) return { error: null, payload: {} }

  const step = readStep()
  const selected = products.value.filter((product) => product.usable && product.checked)
  if (!selected.length) return { error: '请至少选择一个参与组合的产品' }

  const ranges = []
  for (const product of selected) {
    const label = productLabel(product)
    const invalid = (message) => ({ error: `「${label}」${message}` })

    // el-input-number 清空后值为 null，与老版空串同样拦截
    if (product.min === null || product.max === null ||
        !Number.isInteger(product.min) || !Number.isInteger(product.max)) {
      return invalid('的单股下限/上限必须是整数')
    }
    if (product.min < 0 || product.max > 100 || product.min > product.max) {
      return invalid('的单股范围必须满足 0 ≤ 下限 ≤ 上限 ≤ 100')
    }
    if (product.min % step !== 0 || product.max % step !== 0) {
      return invalid(`的单股范围必须是步长 ${step}% 的整数倍（可点「重置范围」按配置比例重算）`)
    }
    ranges.push({
      result_id: product.result_id,
      min_weight: product.min,
      max_weight: product.max,
    })
  }

  return {
    error: null,
    payload: {
      result_ids: selected.map((product) => product.result_id),
      stock_ranges: ranges,
    },
  }
}

function validateBaseParams() {
  const { step, maxWeight, minWeight } = form
  if (step < 1 || step > 100) { ElMessage.warning('权重步长必须在 1-100 之间'); return false }
  if (100 % step !== 0) { ElMessage.warning('权重步长必须能整除 100'); return false }
  if (maxWeight < 1 || maxWeight > 100) { ElMessage.warning('组合总权重上限必须在 1-100 之间'); return false }
  if (minWeight < 0 || minWeight > 100) { ElMessage.warning('组合总权重下限必须在 0-100 之间'); return false }
  if (minWeight > maxWeight) { ElMessage.warning('组合总权重下限不能大于上限'); return false }
  return true
}

// 单股上限只在未启用单股范围时生效，启用后不再校验它的网格约束（服务端同样忽略）
function validateWeights(useRanges) {
  const { step, maxWeight, minWeight, singleCap } = form
  if (!useRanges) {
    if (singleCap < 1 || singleCap > 100) { ElMessage.warning('单只股票权重上限必须在 1-100 之间'); return false }
    if (maxWeight % step !== 0 || minWeight % step !== 0 || singleCap % step !== 0) {
      ElMessage.warning('所有权重参数必须是步长的整数倍')
      return false
    }
    if (singleCap < step) { ElMessage.warning('单只股票权重上限不能小于步长'); return false }
  } else if (maxWeight % step !== 0 || minWeight % step !== 0) {
    ElMessage.warning('组合总权重上下限必须是步长的整数倍')
    return false
  }
  return true
}

// 数据转换：生成 *_disp 字段（原始值 × 100）与展示串（与静态版 transformData 一致）
function transformData(item) {
  item.weight_sum = item.stocks.reduce((sum, stock) => sum + stock.ratio, 0)
  const indexRate = item.annualized_rates?.index
  const startRate = item.annualized_rates?.start
  const indexDd = item.year_max_drawdown?.index
  const startDd = item.year_max_drawdown?.start
  item.index_rate_disp = indexRate != null ? Number(indexRate) * 100 : null
  item.start_rate_disp = startRate != null ? Number(startRate) * 100 : null
  item.index_dd_disp = indexDd != null ? Number(indexDd) * 100 : null
  item.start_dd_disp = startDd != null ? Number(startDd) * 100 : null
  item.stocks_display = item.stocks
    .filter((s) => s.ratio > 0)
    .map((s) => `${s.stock_name || s.stock_code || 'N/A'} (${s.ratio}%)`)
    .join(', ')
  return item
}

async function handleAnalyze() {
  if (analyzing.value) return
  const taskId = form.taskId.trim()
  if (!taskId) {
    ElMessage.warning('请输入任务 ID')
    return
  }
  // 面板尚在加载上一个任务的产品与范围，此时提交会把旧范围发给新任务
  if (productsLoading.value) {
    ElMessage.warning('产品列表加载中，请稍候再试')
    return
  }
  if (!validateBaseParams()) return

  const selection = collectProductSelection()
  if (selection.error) {
    ElMessage.warning(selection.error)
    return
  }
  const useRanges = !!(selection.payload && selection.payload.stock_ranges)
  if (!validateWeights(useRanges)) return

  const payload = {
    task_id: taskId,
    step: form.step,
    max_weight: form.maxWeight,
    min_weight: form.minWeight,
  }
  Object.assign(payload, selection.payload)
  // 启用单股范围后不发送 single_cap：服务端此时不读它，但它的字段级范围约束
  // （>0、≤100）仍会生效，会让一个不生效的值卡住请求。
  if (!useRanges) payload.single_cap = form.singleCap

  analyzing.value = true
  progressVisible.value = true
  rows.value = []
  pendingRows = []
  progressPercent.value = 0
  progressInfo.value = '正在发送请求...'

  let processedCount = 0
  try {
    abortController = new AbortController()
    await analyzeWeightCombinationStream(
      payload,
      {
        signal: abortController.signal,
        onRow(data) {
          pendingRows.push(transformData(data))
          processedCount++
          if (processedCount % 20 === 0) {
            rows.value = rows.value.concat(pendingRows)
            pendingRows = []
            progressPercent.value = -1
            progressInfo.value = `已接收 ${processedCount} 条组合...`
          }
        },
      },
    )
    if (pendingRows.length) {
      rows.value = rows.value.concat(pendingRows)
      pendingRows = []
    }
    progressPercent.value = 100
    progressInfo.value = `分析完成！共生成 ${rows.value.length} 个组合`
    setTimeout(() => {
      progressVisible.value = false
    }, 2000)
  } catch (error) {
    if (error.name === 'AbortError') {
      progressInfo.value = '分析已取消'
      setTimeout(() => {
        progressVisible.value = false
      }, 1500)
    } else {
      progressInfo.value = '分析失败'
      ElMessage.error(`分析失败: ${error.message}`)
    }
  } finally {
    analyzing.value = false
    abortController = null
  }
}

function handleCancel() {
  abortController?.abort()
}

// 携带组合比例新标签打开多品全局预览（与静态版 openGlobalPreviewWithRatios 一致）
function openGlobalPreviewWithRatios(row) {
  if (!form.taskId.trim()) {
    ElMessage.warning('缺少任务 ID，无法跳转全局预览')
    return
  }
  const ratios = (row.stocks || [])
    .filter((s) => s && s.stock_code && Number(s.ratio) > 0)
    .map((s) => ({ stock_code: s.stock_code, ratio: Number(s.ratio) }))
  if (!ratios.length) {
    ElMessage.warning('该组合没有可用的股票比例')
    return
  }
  const { href } = router.resolve({
    name: 'BacktestMultiGlobalPreview',
    params: { id: form.taskId.trim() },
    query: { ratios: JSON.stringify(ratios) },
  })
  window.open(href, '_blank')
}

function exportCsv() {
  // 与静态版 Tabulator table.download('csv') 输出对齐：首列 # 行号，数值按 formatter 带后缀
  const header = ['#', '股票组合', ...numericColumns.map((c) => c.label)]
  const lines = [header]
  filteredRows.value.forEach((row, index) => {
    lines.push([
      String(index + 1),
      `"${row.stocks_display.replace(/"/g, '""')}"`,
      ...numericColumns.map((c) => formatNumber(row[c.prop], c.digits, c.suffix)),
    ])
  })
  const csv = '\uFEFF' + lines.map((line) => line.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `weight_combination_${Date.now()}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  const taskId = route.query.task_id
  if (taskId) {
    form.taskId = String(taskId)
    // 老版 prefillTaskIdFromUrl：URL 带任务 ID 时自动加载产品面板
    loadProducts(String(taskId))
  }
})

onBeforeUnmount(() => {
  abortController?.abort()
  productsAbort?.abort()
})
</script>

<style scoped>
.weight-combination-page__task-id-input {
  width: 220px;
}

.weight-combination-page__section {
  margin-bottom: 16px;
}

.weight-combination-page__progress-info {
  margin-top: 8px;
  font-size: var(--app-font-xs, 12px);
  color: var(--app-text-muted, #909399);
}

.weight-combination-page__results-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.weight-combination-page__stat {
  margin-left: 8px;
}

.weight-combination-page__col-head {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.weight-combination-page__funnel {
  color: var(--app-text-muted, #909399);
}

.weight-combination-page__funnel.is-active {
  color: var(--el-color-primary);
}

.weight-combination-page__filter {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weight-combination-page__filter-hint {
  font-size: var(--app-font-xs, 12px);
  color: var(--el-color-danger);
}

.weight-combination-page__filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.weight-combination-page__products {
  margin-top: 12px;
}

.weight-combination-page__products-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.weight-combination-page__products-hint {
  margin: 8px 0;
}

.weight-combination-page__product-row--off {
  opacity: 0.55;
}
</style>
