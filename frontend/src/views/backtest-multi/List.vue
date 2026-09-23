<template>
  <div class="app-page backtest-multi-list-page">
    <PageToolbar
      eyebrow="Multi-Product Backtest"
      title="多产品回测中心"
      description="集中查看多产品回测任务状态、运行情况和入口操作，快速进入详情或创建新任务。"
    >
      <template #actions>
        <el-tag size="large" type="info" class="backtest-multi-list-page__refresh-badge">
          最后刷新：<span class="backtest-multi-list-page__refresh-time">{{ lastUpdated }}</span>
        </el-tag>
        <el-button type="success" plain @click="openBatchExport">批量导出</el-button>
        <el-button type="primary" @click="$router.push('/backtest-multi/create')">创建新任务</el-button>
      </template>
    </PageToolbar>

    <StatCardGrid :cards="statCards" :data="stats" />

    <FilterToolbar
      v-model="filters"
      :filters="filterDefs"
      @search="doFilter"
      @clear="clearFilters"
    />

    <DataTableCard
      :data="tasks"
      :loading="loading"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      @page-change="loadTasks"
    >
      <el-table-column label="任务名称 & ID" min-width="200">
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(detailRoute(row))">{{ row.name || '未命名任务' }}</el-link>
          <div class="inline-muted font-mono">
            ID: {{ row.id?.slice(0, 8) }} · 产品:
            <span v-if="productChipItems(row).length" class="product-chip-wrap">
              <span
                v-for="(item, index) in productChipItems(row).slice(0, PRODUCT_CHIPS_MAX_VISIBLE)"
                :key="index"
                class="product-chip product-chip--toggle"
                role="button"
                tabindex="0"
                aria-haspopup="dialog"
                :title="item.title || item.label"
                @click.stop="openProductList(row)"
                @keydown.enter.prevent="openProductList(row)"
                @keydown.space.prevent="openProductList(row)"
              >{{ item.label }}</span>
              <span
                v-if="productChipItems(row).length > PRODUCT_CHIPS_MAX_VISIBLE"
                class="product-chip product-chip--more product-chip--toggle"
                role="button"
                tabindex="0"
                aria-haspopup="dialog"
                @click.stop="openProductList(row)"
                @keydown.enter.prevent="openProductList(row)"
                @keydown.space.prevent="openProductList(row)"
              >+{{ productChipItems(row).length - PRODUCT_CHIPS_MAX_VISIBLE }}</span>
            </span>
            <span v-else>-</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="模型版本" width="130">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ inferModelVersion(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="K线范围" width="190">
        <template #default="{ row }">{{ klineRangeText(row) }}</template>
      </el-table-column>
      <el-table-column label="执行参数" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ buildExecutionParamsText(row) || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="140">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="开始时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.start_time) }}
        </template>
      </el-table-column>
      <el-table-column label="结束时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.end_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(detailRoute(row))">详情</el-button>
          <el-button link type="danger" @click="handleDeleteTask(row)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <!-- 批量导出弹窗（静态版 batchExportModal 翻译） -->
    <el-dialog v-model="batchExportVisible" title="批量导出当前页任务" width="720px" top="6vh">
      <el-alert
        title="已完成任务可选，导出为 ZIP，最多 10 个。"
        type="info"
        :closable="false"
        class="backtest-multi-list-page__export-tip"
      />
      <div class="backtest-multi-list-page__export-summary">
        <div class="backtest-multi-list-page__export-count">{{ batchExportSummary }}</div>
        <div class="backtest-multi-list-page__export-actions">
          <el-button size="small" @click="selectAllExportableTasks">全选当前页</el-button>
          <el-button size="small" @click="selectAllExportableTasks">仅已完成任务</el-button>
          <el-button size="small" @click="clearBatchExportSelection">清空</el-button>
        </div>
      </div>
      <div class="backtest-multi-list-page__export-list">
        <div v-if="!tasks.length" class="panel-note panel-note--center">当前页暂无可展示任务</div>
        <div
          v-for="task in tasks"
          :key="task.id"
          :class="['backtest-multi-list-page__export-card', {
            'is-selected': selectedBatchExportTaskIds.has(String(task.id)),
            'is-disabled': task.status !== 'completed',
          }]"
          role="button"
          @click="toggleBatchExportTask(task)"
        >
          <el-checkbox
            :model-value="selectedBatchExportTaskIds.has(String(task.id))"
            :disabled="task.status !== 'completed'"
            @click.prevent
          />
          <div class="backtest-multi-list-page__export-card-main">
            <div class="backtest-multi-list-page__export-card-title">{{ task.name || '未命名任务' }}</div>
            <div class="panel-note" :title="productDetailText(task)">ID: {{ String(task.id || '').slice(0, 8) }} · 产品: {{ productNamesText(task) }}</div>
            <div class="panel-note">模型版本：{{ inferModelVersion(task) }} · 创建：{{ formatDateTime(task.created_at) }}</div>
            <div v-if="task.status !== 'completed'" class="panel-note">尚未完成，不可导出</div>
          </div>
          <StatusTag :status="task.status" />
        </div>
      </div>
      <template #footer>
        <div class="backtest-multi-list-page__export-footer">
          <span class="panel-note">ZIP 内每个任务保留原全局预览 XLSX 格式。</span>
          <div>
            <el-button @click="batchExportVisible = false">取消</el-button>
            <el-button type="success" :disabled="selectedBatchExportTaskIds.size < 1" :loading="exportingBatch" @click="exportSelectedBatchTasks">
              导出 ZIP
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 产品清单弹窗（静态版 productListModal 翻译） -->
    <el-dialog v-model="productListVisible" :title="productListTitle" width="640px" top="8vh">
      <div class="panel-note backtest-multi-list-page__product-count">共 {{ productListRows.length }} 个产品</div>
      <el-table :data="productListRows" size="small" max-height="420">
        <el-table-column prop="name" label="产品名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="code" label="股票代码" width="130" />
        <el-table-column prop="market" label="市场" width="90" />
      </el-table>
      <template #footer>
        <el-button @click="productListVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, deleteTask as deleteTaskApi } from '@/api/task'
import { exportGlobalPreviewsBatch } from '@/api/backtestMulti'
import { initialListPagination, writeJsonStorage, replaceQuery } from '@/utils/pageState'
import { formatDateTime } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import StatusTag from '@/components/StatusTag.vue'
import { usePolling } from '@/composables/usePolling'

const route = useRoute()
const router = useRouter()
const LIST_KEY = 'backtest_multi_product:list_pagination'
const initialPagination = initialListPagination(route.query, LIST_KEY, 20)
const tasks = ref([])
const loading = ref(false)
const page = ref(initialPagination.page)
const pageSize = ref(initialPagination.perPage)
const total = ref(0)
const stats = ref({})
const lastUpdated = ref('-')
const filters = reactive({ status: '', keyword: '', stock_code: '' })

// ===== 批量导出状态（静态版 list.js 翻译） =====
const BATCH_EXPORT_MAX_TASKS = 10
const batchExportVisible = ref(false)
const exportingBatch = ref(false)
const selectedBatchExportTaskIds = reactive(new Set())

const statCards = [
  { key: 'total', label: '任务总数', color: '#2563eb' },
  { key: 'running', label: '运行中', color: '#f59e0b' },
  { key: 'completed', label: '已完成', color: '#16a34a' },
  { key: 'failed', label: '执行失败', color: '#ef4444' },
]

const filterDefs = [
  { key: 'status', type: 'select', placeholder: '任务状态', span: { xs: 24, sm: 6 }, options: [
    { value: 'pending', label: '待执行' },
    { value: 'running', label: '运行中' },
    { value: 'completed', label: '已完成' },
    { value: 'cancelled', label: '已取消' },
    { value: 'error', label: '错误' },
  ]},
  { key: 'keyword', type: 'input', placeholder: '任务名称 / ID', span: { xs: 24, sm: 8 } },
  { key: 'stock_code', type: 'input', placeholder: '股票代码（如 AAPL.US）', span: { xs: 24, sm: 8 } },
]

// ===== 表格展示辅助（静态版 inferModelVersion / buildKlineRangeText / buildExecutionParamsText） =====
function extractModelVersionLabel(title) {
  const normalized = String(title || '').toUpperCase()
  if (normalized.includes('C7.0.3')) return 'C7.0.3'
  if (normalized.includes('C7')) return 'C7'
  if (normalized.includes('C5')) return 'C5'
  if (normalized.includes('C4')) return 'C4'
  if (normalized.includes('C3') || normalized.includes('CHARTING:3')) return 'C3'
  return ''
}

// 按 config 内各产品 sheet 标题提取模型版本（与后端 get_backtest_model_version 同口径）。
function inferModelVersion(task) {
  const products = Array.isArray(task.config?.products) ? task.config.products : []
  const versions = [...new Set(products
    .map((product) => extractModelVersionLabel(product.sheet?.title))
    .filter(Boolean))]
  const versionText = versions.join('-') || '-'
  return products.length ? `${versionText} · ${products.length}品` : versionText
}

function klineRangeText(task) {
  const config = task.config || {}
  if (!config.start_date && !config.end_date) {
    return '-'
  }
  return `${config.start_date || '-'} ~ ${config.end_date || '-'}`
}

// 执行参数跨产品去重：参数行完全相同只展示一次。
function buildExecutionParamsText(task) {
  const products = Array.isArray(task.config?.products) ? task.config.products : []
  const seen = new Set()
  const uniqueRows = []
  products.forEach((product) => {
    (Array.isArray(product.parameters) ? product.parameters : []).forEach((row) => {
      const key = JSON.stringify(row)
      if (seen.has(key)) {
        return
      }
      seen.add(key)
      uniqueRows.push((Array.isArray(row) ? row : [row]).join('/'))
    })
  })
  return uniqueRows.join('；')
}

function productNamesText(task) {
  const products = Array.isArray(task.config?.products) ? task.config.products : []
  return products.map((item) => item.product_name || item.stock_code).filter(Boolean).join(' / ') || '-'
}

// ===== 产品股票 chip（与静态版 backtest_multi_product_list.js 同口径） =====
// 折叠阈值：超出后收敛为 +N，悬停 title 查看剩余全量。
const PRODUCT_CHIPS_MAX_VISIBLE = 3

// chip 口径与详情页产品卡一致：主文本 product_name，title 补 stock_code / market_type。
function productChipLabel(product) {
  return String(product.product_name || product.name || product.stock_code || '').trim()
}

function productChipTitle(product) {
  const name = String(product.product_name || product.name || '').trim()
  const details = [String(product.stock_code || '').trim(), String(product.market_type || '').trim()].filter(Boolean)
  if (name && details.length) return `${name}（${details.join(' · ')}）`
  return name || details.join(' · ')
}

function productChipItems(task) {
  const products = Array.isArray(task.config?.products) ? task.config.products : []
  return products
    .map((product) => ({ label: productChipLabel(product), title: productChipTitle(product) }))
    .filter((item) => item.label)
}

function productDetailText(task) {
  return productChipItems(task).map((item) => item.title || item.label).join('；')
}

// ===== 产品清单表格弹窗（与静态版 productListModal 同构） =====
const productListVisible = ref(false)
const productListTask = ref(null)

function buildProductListRows(task) {
  const products = Array.isArray(task?.config?.products) ? task.config.products : []
  return products.map((product, index) => ({
    name: String(product.product_name || product.name || '').trim() || `产品 ${index + 1}`,
    code: String(product.stock_code || '').trim() || '-',
    market: String(product.market_type || '').trim() || '-',
  }))
}

const productListRows = computed(() => buildProductListRows(productListTask.value))

const productListTitle = computed(() => (
  `产品清单${productListTask.value?.name ? ` · ${productListTask.value.name}` : ''}`
))

function openProductList(task) {
  productListTask.value = task
  productListVisible.value = true
}

// ===== 列表加载（silent=true 供轮询复用，不闪 loading） =====
async function loadTasks({ silent = false } = {}) {
  if (!silent) {
    loading.value = true
  }
  try {
    const params = { page: page.value, per_page: pageSize.value, task_type: 'backtest_multi_product' }
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.stock_code) params.stock_code = filters.stock_code

    const res = await getTasks(params)
    tasks.value = res.items || []
    total.value = res.total || 0
    lastUpdated.value = formatDateTime(new Date().toISOString())

    // 分页状态落 localStorage + URL（与静态版 persistListPaginationState 一致）
    writeJsonStorage(LIST_KEY, { page: page.value, per_page: pageSize.value })
    replaceQuery(router, route, { page: String(page.value), per_page: String(pageSize.value) })

    const s = res.statistics || {}
    stats.value = {
      total: s.total_tasks ?? res.total ?? 0,
      running: (s.running_tasks ?? 0) + (s.pending_tasks ?? 0),
      completed: s.completed_tasks ?? 0,
      failed: s.error_tasks ?? 0,
    }
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

function detailRoute(row) {
  return { path: `/backtest-multi/${row.id}`, query: { list_page: String(page.value), list_per_page: String(pageSize.value) } }
}

function doFilter() {
  page.value = 1
  loadTasks()
}

function clearFilters() {
  filters.status = ''
  filters.keyword = ''
  filters.stock_code = ''
  doFilter()
}

// ===== 行内删除（静态版 deleteTask + 末页回退） =====
async function handleDeleteTask(row) {
  try {
    await ElMessageBox.confirm(`确认删除任务 ${row.id} 吗？`, '删除任务', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTaskApi(row.id)
    ElMessage.success('任务已删除')
    // 末页只剩一条时回退一页，避免停留在空页。
    const isLastItemOnPage = tasks.value.length <= 1
    if (isLastItemOnPage && page.value > 1 && total.value > 1) {
      page.value -= 1
    }
    loadTasks()
  } catch (error) {
    ElMessage.error(`删除失败：${error.message || '未知错误'}`)
  }
}

// ===== 批量导出 =====
const exportableTasks = computed(() => tasks.value.filter((task) => task.status === 'completed'))

const batchExportSummary = computed(() => (
  `当前页 ${tasks.value.length} 个任务，可导出 ${exportableTasks.value.length} 个，已选 ${selectedBatchExportTaskIds.size} 个`
))

function openBatchExport() {
  // 打开弹窗时清理已不在当前页的选中项（静态版 renderBatchExportTaskList 前置清理）
  const knownIds = new Set(tasks.value.map((task) => String(task.id || '')))
  ;[...selectedBatchExportTaskIds].forEach((taskId) => {
    if (!knownIds.has(taskId)) {
      selectedBatchExportTaskIds.delete(taskId)
    }
  })
  batchExportVisible.value = true
}

function toggleBatchExportTask(task) {
  const taskId = String(task.id || '')
  if (task.status !== 'completed') {
    return
  }
  if (selectedBatchExportTaskIds.has(taskId)) {
    selectedBatchExportTaskIds.delete(taskId)
  } else if (selectedBatchExportTaskIds.size < BATCH_EXPORT_MAX_TASKS) {
    selectedBatchExportTaskIds.add(taskId)
  } else {
    ElMessage.warning(`批量导出最多支持 ${BATCH_EXPORT_MAX_TASKS} 个任务`)
  }
}

function selectAllExportableTasks() {
  selectedBatchExportTaskIds.clear()
  exportableTasks.value.slice(0, BATCH_EXPORT_MAX_TASKS).forEach((task) => {
    selectedBatchExportTaskIds.add(String(task.id))
  })
}

function clearBatchExportSelection() {
  selectedBatchExportTaskIds.clear()
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

async function exportSelectedBatchTasks() {
  const taskIds = [...selectedBatchExportTaskIds]
  if (!taskIds.length) {
    return
  }
  exportingBatch.value = true
  try {
    const { blob, filename } = await exportGlobalPreviewsBatch(taskIds)
    downloadBlob(blob, filename)
    batchExportVisible.value = false
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  } finally {
    exportingBatch.value = false
  }
}

// 静态版同款轮询（1 分钟一次，静默不闪 loading）+ 「最后刷新」徽章
usePolling(() => loadTasks({ silent: true }), { interval: 60 * 1000 })
</script>

<style lang="scss" scoped>
.backtest-multi-list-page__refresh-badge {
  margin-right: 4px;
}

/* 产品股票 chip：局部恢复换行，超出 PRODUCT_CHIPS_MAX_VISIBLE 折叠为 +N（对齐静态版样式）。 */
.product-chip-wrap {
  white-space: normal;
}

.product-chip {
  display: inline-block;
  max-width: 140px;
  margin: 1px 2px 1px 0;
  padding: 0 7px;
  border: 1px solid var(--app-border, var(--el-border-color, #dcdfe6));
  border-radius: 999px;
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-text-color-secondary, #909399);
  font-family: var(--el-font-family, inherit);
  font-size: 12px;
  line-height: 18px;
  vertical-align: bottom;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-chip--more {
  cursor: help;
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
  border-color: var(--el-color-primary-light-5, #79bbff);
  background: var(--el-color-primary-light-9, #ecf5ff);
}

/* 可点击 chip：打开产品清单表格弹窗（对齐静态版样式）。 */
.product-chip--toggle {
  cursor: pointer;
}

.product-chip--toggle:hover,
.product-chip--toggle:focus-visible {
  color: var(--el-color-primary, #409eff);
  border-color: var(--el-color-primary-light-5, #79bbff);
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.backtest-multi-list-page__product-count {
  margin-bottom: 10px;
}

.backtest-multi-list-page__refresh-time {
  font-family: var(--el-font-family, inherit);
}

.backtest-multi-list-page__export-tip {
  margin-bottom: 12px;
}

.backtest-multi-list-page__export-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
}

.backtest-multi-list-page__export-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.backtest-multi-list-page__export-list {
  display: grid;
  gap: 8px;
  max-height: 46vh;
  overflow: auto;
}

.backtest-multi-list-page__export-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;

  &:hover {
    border-color: var(--el-color-primary-light-5, #79bbff);
  }

  &.is-selected {
    border-color: var(--el-color-primary, #409eff);
    background: var(--el-color-primary-light-9, #ecf5ff);
  }

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }
}

.backtest-multi-list-page__export-card-main {
  flex: 1;
  min-width: 0;
}

.backtest-multi-list-page__export-card-title {
  font-weight: 600;
  color: var(--app-text);
}

.backtest-multi-list-page__export-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  > div {
    display: flex;
    gap: 8px;
  }
}
</style>
