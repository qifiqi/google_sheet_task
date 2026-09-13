<template>
  <div class="app-page backtest-multi-detail-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Multi-Product Monitor</div>
        <h2 class="page-title">{{ task?.name || '多产品回测详情' }}</h2>
        <p class="page-description">
          Task ID: <span class="font-mono">{{ taskId }}</span>
        </p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.push({ path: '/backtest-multi/list', query: backListQuery })">返回列表</el-button>
        <el-button type="success" plain @click="$router.push({ path: `/backtest-multi/${taskId}/global-preview`, query: pagingLink() })">全局预览页</el-button>
        <el-button type="primary" plain @click="$router.push({ path: '/performance_analysis/weight_combination', query: { ...pagingLink(), task_id: taskId } })">权重组合分析</el-button>
        <el-button
          type="warning"
          :disabled="!canStop || taskActionInProgress"
          @click="handleStopTask"
        >停止任务</el-button>
        <el-button
          type="warning"
          plain
          :disabled="taskActionInProgress"
          @click="handleResumeRestartTask"
        >断点重启</el-button>
        <el-button
          type="danger"
          plain
          :disabled="taskActionInProgress"
          @click="handleRestartFromScratch"
        >重头开始</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-row v-if="task" :gutter="16" class="backtest-multi-detail-page__metrics">
        <el-col :xs="24" :md="10">
          <el-card shadow="never" class="page-section">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">基础执行信息</h3>
            </div>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="任务名称">{{ task.name }}</el-descriptions-item>
              <el-descriptions-item label="任务 ID">
                <span class="inline-muted font-mono">{{ task.id }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <StatusTag :status="task.status" />
              </el-descriptions-item>
              <el-descriptions-item label="进度">
                <TaskProgressCell :current-step="task.current_step || 0" :total-steps="task.total_steps || 0" />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8">
          <el-card shadow="never" class="page-section">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">时间信息</h3>
            </div>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="创建时间">{{ task.created_at || '-' }}</el-descriptions-item>
              <el-descriptions-item label="开始执行时间">{{ task.start_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="结束时间">{{ task.end_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="执行时长">
                {{ task.duration_seconds != null ? `${task.duration_seconds}s` : '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="6">
          <div class="hero-panel">
            <div class="hero-panel__eyebrow">Execution Summary</div>
            <div class="backtest-multi-detail-page__hero-stats">
              <div class="backtest-multi-detail-page__hero-stat">
                <div class="backtest-multi-detail-page__hero-value">{{ resultTotal }}</div>
                <div class="backtest-multi-detail-page__hero-label">结果总数</div>
              </div>
              <div class="backtest-multi-detail-page__hero-stat">
                <div class="backtest-multi-detail-page__hero-value">{{ task.current_step || 0 }}/{{ task.total_steps || 0 }}</div>
                <div class="backtest-multi-detail-page__hero-label">执行进度（步）</div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-card v-if="task" shadow="never" class="page-section">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="任务日志" name="logs">
            <div class="backtest-multi-detail-page__log-toolbar">
              <span class="panel-note">自动刷新：1 分钟</span>
              <span class="panel-note">最近刷新：{{ logLastUpdated }}</span>
              <el-button size="small" type="primary" plain @click="handleManualRefresh">刷新日志</el-button>
            </div>
            <div ref="logContainerRef" class="backtest-multi-detail-page__log-panel">
              <div v-if="!logs.length" class="panel-note panel-note--center">暂无日志</div>
              <div v-for="(log, index) in logs" :key="index" :class="['log-line', `log-${log.level}`]">
                [{{ log.timestamp }}] [{{ (log.level || 'info').toUpperCase() }}] {{ log.message }}
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="回测生成结果" name="results">
            <el-table :data="results" stripe>
              <el-table-column prop="id" label="结果 ID" min-width="150">
                <template #default="{ row }">
                  <span class="font-mono">{{ row.id }}</span>
                </template>
              </el-table-column>
              <el-table-column label="执行参数" min-width="360">
                <template #default="{ row }">
                  <div v-if="paramChips(row.parameters).length" class="backtest-multi-detail-page__param-summary">
                    <div class="backtest-multi-detail-page__param-main">
                      <el-tag
                        v-for="(chip, chipIndex) in paramChips(row.parameters).filter((chip) => chip.primary)"
                        :key="`p-${chipIndex}`"
                        size="small"
                        type="info"
                        class="backtest-multi-detail-page__chip"
                      >
                        <strong>{{ chip.label }}</strong>&nbsp;{{ chip.value }}
                      </el-tag>
                    </div>
                    <div class="backtest-multi-detail-page__param-detail">
                      <el-tag
                        v-for="(chip, chipIndex) in paramChips(row.parameters).filter((chip) => !chip.primary)"
                        :key="`d-${chipIndex}`"
                        size="small"
                        class="backtest-multi-detail-page__chip"
                      >
                        <strong>{{ chip.label }}</strong>&nbsp;{{ chip.value }}
                      </el-tag>
                    </div>
                  </div>
                  <span v-else class="panel-note">-</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                    {{ row.success ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="创建时间" width="170" show-overflow-tooltip>
                <template #default="{ row }">{{ formatDateTime(row.timestamp) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="110">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewResult(row)">查看结果</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="backtest-multi-detail-page__pagination">
              <el-pagination
                v-model:current-page="resultPage"
                v-model:page-size="resultPageSize"
                :total="resultTotal"
                layout="total, prev, pager, next"
                @current-change="loadResults"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane label="任务输入参数" name="params">
            <div class="backtest-multi-detail-page__param-toolbar">
              <el-button size="small" @click="copyAllTaskParameters">
                <el-icon class="el-icon--left"><CopyDocument /></el-icon>复制全部参数
              </el-button>
            </div>
            <el-table :data="productRows" stripe>
              <el-table-column label="产品" min-width="160">
                <template #default="{ row }">{{ row.label }}</template>
              </el-table-column>
              <el-table-column label="股票/市场" min-width="140">
                <template #default="{ row }">{{ row.stockMarket }}</template>
              </el-table-column>
              <el-table-column label="比例" width="90">
                <template #default="{ row }">{{ row.ratio }}</template>
              </el-table-column>
              <el-table-column label="Sheet" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ row.sheet }}</template>
              </el-table-column>
              <el-table-column label="参数行数" width="90">
                <template #default="{ row }">{{ row.paramCount }}</template>
              </el-table-column>
              <el-table-column label="详情" width="90" align="center">
                <template #default="{ row }">
                  <el-button size="small" type="primary" plain @click="openProductParameterModal(row.index)">
                    <el-icon><View /></el-icon>
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="任务运行配置" name="config">
            <div class="backtest-multi-detail-page__config-grid">
              <div v-for="item in taskConfigItems" :key="item.label" class="backtest-multi-detail-page__config-item">
                <div class="backtest-multi-detail-page__config-label">{{ item.label }}</div>
                <div class="backtest-multi-detail-page__config-value">{{ item.value }}</div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <el-dialog v-model="paramModalVisible" :title="paramModal.title" width="860px" top="6vh">
      <div class="panel-note backtest-multi-detail-page__modal-subtitle">{{ paramModal.subtitle }}</div>
      <div class="backtest-multi-detail-page__modal-meta">
        <el-tag size="small" type="info">模型 {{ paramModal.modelLabel }}</el-tag>
        <el-tag size="small" type="info">{{ paramModal.stockCode }}</el-tag>
        <el-tag size="small" type="info">{{ paramModal.ratio }}%</el-tag>
      </div>
      <div v-if="!paramModal.rows.length" class="panel-note panel-note--center backtest-multi-detail-page__modal-empty">
        暂无参数
      </div>
      <el-table v-else :data="paramModal.rows" border size="small" max-height="480">
        <el-table-column label="#" type="index" width="56" />
        <el-table-column
          v-for="field in paramModal.fields"
          :key="field.key"
          :label="field.label"
          min-width="110"
        >
          <template #default="{ row }">{{ row[field.key] ?? '' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listQueryFromRoute, initialResultPagination, paginationLinkQuery, writeJsonStorage, replaceQuery } from '@/utils/pageState'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, View } from '@element-plus/icons-vue'
import { getTaskResults } from '@/api/backtestMulti'
import {
  getTask,
  getTaskLogs,
  cancelTask,
  restartTask
} from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import { usePolling } from '@/composables/usePolling'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const taskId = route.params.id
const task = ref(null)
const logs = ref([])
const results = ref([])
const loading = ref(false)
const activeTab = ref('logs')
const logContainerRef = ref()
const logLastUpdated = ref('-')
const taskActionInProgress = ref(false)
// 分页状态链（自静态版翻译）：回列表/跳结果/跳全局预览统一携带分页上下文
const LIST_PAGING_KEY = 'backtest_multi_product:list_pagination'
const RESULT_PAGING_KEY = `backtest_multi_product:task_results:${taskId}:pagination`
const listState = listQueryFromRoute(route.query, LIST_PAGING_KEY, 20)
const backListQuery = { page: String(listState.page), per_page: String(listState.perPage) }
const initialResultPaging = initialResultPagination(route.query, RESULT_PAGING_KEY, 10)
const resultPage = ref(initialResultPaging.page)
const resultPageSize = ref(initialResultPaging.perPage)

function pagingLink() {
  return paginationLinkQuery(listState, { page: resultPage.value, perPage: resultPageSize.value })
}
const resultTotal = ref(0)

const canStop = computed(() => {
  const status = task.value?.status
  // 静态版语义：pending 与 running 都允许停止。
  return status === 'pending' || status === 'running'
})

// ===== 任务运行配置（静态版 renderTaskConfig 字段翻译） =====
const taskConfigItems = computed(() => {
  const config = task.value?.config || {}
  const products = Array.isArray(config.products) ? config.products : []
  const weightingModeLabels = {
    daily_compound: '日收益加权复利',
    legacy_cumulative: '旧版累计收益加权（已停用）'
  }
  const items = [
    { label: 'K线开始日期', value: config.start_date },
    { label: 'K线结束日期', value: config.end_date },
    { label: '产品数量', value: products.length },
    { label: '加权算法', value: weightingModeLabels[config.weighting_mode] || config.weighting_mode },
    { label: 'K线数据源', value: config.kline_data_source },
    { label: '固定产品批次', value: config.fixed_product_batch_id },
    { label: 'Token ID', value: config.token_id },
    { label: 'Token 名称', value: config.token_name },
    { label: 'Token 类型', value: config.token_type },
    { label: 'Token 任务类型', value: config.token_task_type },
    { label: 'Token 文件', value: config.token_file },
  ]
  return items.map((item) => ({
    label: item.label,
    value: formatConfigDisplayValue(item.value),
  }))
})

function formatConfigDisplayValue(value) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(', ') : '-'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

// ===== 产品参数表（静态版 FIELD_MAP / inferProductModelVersion） =====
const DETAIL_FIELD_MAP = {
  c7: [
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'ml', label: 'ML (ml)' }
  ],
  c5: [
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'ml', label: 'ML (ml)' }
  ],
  c3: [
    { key: 'commission', label: 'Commission' },
    { key: 'xm', label: 'X Multiplier (xm)' },
    { key: 'dbbh1', label: '单边保护1' },
    { key: 'dbbh2', label: '单边保护2' },
    { key: 'zlxc', label: '中立限仓' },
    { key: 'zsgz', label: '指数跟踪' },
    { key: 'ywf1', label: '一窝蜂 smoothing' },
    { key: 'ywf2', label: '一窝蜂 bordering' }
  ]
}

function inferProductModelVersion(product) {
  const sheet = product?.sheet || {}
  const text = [
    product?.model_version,
    product?.product_name,
    product?.name,
    sheet.title,
    sheet.sheet_name
  ].filter(Boolean).join(' ').toUpperCase()
  if (text.includes('C7')) {
    return 'c7'
  }
  return text.includes('C5') || text.includes('C4') ? 'c5' : 'c3'
}

function getProductParameterFields(product) {
  const version = inferProductModelVersion(product)
  return DETAIL_FIELD_MAP[version] || DETAIL_FIELD_MAP.c3
}

const configProducts = computed(() => {
  const config = task.value?.config || {}
  return Array.isArray(config.products) ? config.products : []
})

const productRows = computed(() => configProducts.value.map((product, index) => {
  const sheet = product.sheet || {}
  const parameters = Array.isArray(product.parameters) ? product.parameters : []
  return {
    index,
    label: product.product_name || product.name || `产品 ${index + 1}`,
    stockMarket: `${product.stock_code || '-'} / ${product.market_type || '-'}`,
    ratio: `${product.ratio || '-'}%`,
    sheet: sheet.title || sheet.sheet_name || sheet.spreadsheet_id || '-',
    paramCount: parameters.length,
  }
}))

// 参数详情弹窗
const paramModalVisible = ref(false)
const paramModal = ref({
  title: '',
  subtitle: '',
  modelLabel: 'C3',
  stockCode: '-',
  ratio: '-',
  fields: [],
  rows: [],
})

function openProductParameterModal(productIndex) {
  const product = configProducts.value[productIndex]
  if (!product) {
    return
  }
  const parameters = Array.isArray(product.parameters) ? product.parameters : []
  const fields = getProductParameterFields(product)
  const sheet = product.sheet || {}
  paramModal.value = {
    title: `${product.product_name || product.name || `产品 ${productIndex + 1}`} 参数详情`,
    subtitle: [
      product.stock_code ? `股票：${product.stock_code}` : '',
      product.market_type ? `市场：${product.market_type}` : '',
      sheet.title || sheet.sheet_name ? `Sheet：${sheet.title || sheet.sheet_name}` : '',
      `参数行数：${parameters.length}`
    ].filter(Boolean).join(' · '),
    modelLabel: inferProductModelVersion(product).toUpperCase(),
    stockCode: product.stock_code || '-',
    ratio: String(product.ratio ?? '-'),
    fields,
    rows: parameters.map((row) => {
      const values = Array.isArray(row) ? row : []
      const rowItem = {}
      fields.forEach((field, index) => {
        rowItem[field.key] = values[index] ?? ''
      })
      return rowItem
    }),
  }
  paramModalVisible.value = true
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

function allProductParametersToClipboard(products) {
  return (products || []).map((product, index) => {
    const productName = product.product_name || product.name || `产品 ${index + 1}`
    const rows = (Array.isArray(product.parameters) ? product.parameters : [])
      .filter((row) => Array.isArray(row) && row.some((value) => String(value ?? '').trim()))
      .map((row) => row.join('\t'))
      .join('\n')
    return rows ? `# ${productName}\n${rows}` : ''
  }).filter(Boolean).join('\n\n')
}

async function copyAllTaskParameters() {
  try {
    const text = allProductParametersToClipboard(configProducts.value)
    if (!text) {
      throw new Error('当前任务没有可复制的参数')
    }
    await writeClipboardText(text)
    ElMessage.success('全部产品参数已复制')
  } catch (error) {
    ElMessage.error(error.message || '复制参数失败')
  }
}

// ===== 结果表执行参数摘要（静态版 summarizeParameters） =====
function stringifyCompact(value) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function truncate(text, length) {
  return String(text).length > length ? `${String(text).slice(0, length)}...` : String(text)
}

function paramChips(parameters) {
  if (parameters === null || parameters === undefined) {
    return []
  }
  if (Array.isArray(parameters)) {
    return parameters.map((item, index) => ({
      primary: false,
      label: `参数 ${index + 1}`,
      value: truncate(stringifyCompact(item), 40),
    }))
  }
  if (typeof parameters === 'object') {
    const entries = Object.entries(parameters)
    if (!entries.length) {
      return []
    }
    const kline = Array.isArray(parameters.kline) ? parameters.kline : []
    const parameterValues = Array.isArray(parameters.parameter) ? parameters.parameter : []
    const chips = []
    if (parameters.product_name) {
      chips.push({ primary: true, label: '产品', value: String(parameters.product_name) })
    }
    if (parameters.stock_code) {
      chips.push({ primary: true, label: '股票', value: String(parameters.stock_code) })
    }
    if (parameters.ratio !== undefined && parameters.ratio !== null && parameters.ratio !== '') {
      chips.push({ primary: true, label: '比例', value: `${String(parameters.ratio)}%` })
    }
    if (kline.length) {
      const firstDate = kline[0] && kline[0].stock_date ? String(kline[0].stock_date) : '-'
      const lastDate = kline[kline.length - 1] && kline[kline.length - 1].stock_date ? String(kline[kline.length - 1].stock_date) : '-'
      chips.push({ primary: true, label: 'K线范围', value: `${firstDate} ~ ${lastDate}` })
    }
    const hiddenKeys = [
      'stock_code', 'year', 'Kline_key', 'kline', 'parameter', 'product_name',
      'parameter_group_index', 'product_index', 'ratio', 'sheet',
      'start_date', 'end_date'
    ]
    entries
      .filter(([key]) => !hiddenKeys.includes(key))
      .forEach(([key, value]) => {
        chips.push({ primary: false, label: key, value: truncate(stringifyCompact(value), 36) })
      })
    parameterValues.forEach((value, index) => {
      chips.push({ primary: false, label: `P${index + 1}`, value: truncate(stringifyCompact(value), 24) })
    })
    return chips
  }
  return [{ primary: false, label: '参数', value: String(parameters) }]
}

// ===== 数据加载（silent=true 时只拉数据不弹错误，供轮询复用；与静态版 loadXxx({silent}) 一致） =====
async function loadTask({ silent = false } = {}) {
  try {
    const res = await getTask(taskId)
    task.value = res.task || res
  } catch (error) {
    if (!silent && !loading.value) {
      ElMessage.error(error.message || '加载任务失败')
    }
  }
}

async function loadLogs({ silent = false } = {}) {
  try {
    const res = await getTaskLogs(taskId)
    const container = logContainerRef.value
    const wasNearBottom = container
      ? container.scrollTop + container.clientHeight >= container.scrollHeight - 12
      : true
    logs.value = res.logs || []
    logLastUpdated.value = formatDateTime(new Date().toISOString())
    if (wasNearBottom) {
      nextTick(() => {
        if (logContainerRef.value) {
          logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
        }
      })
    }
  } catch (error) {
    logLastUpdated.value = formatDateTime(new Date().toISOString())
    if (!silent && !loading.value) {
      ElMessage.error(error.message || '加载任务日志失败')
    }
  }
}

async function loadResults({ silent = false } = {}) {
  try {
    const res = await getTaskResults(taskId, { page: resultPage.value, per_page: resultPageSize.value })
    results.value = res.items || []
    resultTotal.value = res.total || 0
    writeJsonStorage(RESULT_PAGING_KEY, { page: resultPage.value, per_page: resultPageSize.value })
    replaceQuery(router, route, { result_page: String(resultPage.value), result_per_page: String(resultPageSize.value) })
  } catch (error) {
    if (!silent && !loading.value) {
      ElMessage.error(error.message || '加载回测结果失败')
    }
  }
}

// 结果行跳结果页：携带 resultId（非任务 ID）与四参分页（静态版 buildResultHref）。
function viewResult(row) {
  router.push({
    path: `/backtest-multi/${row.id}/result`,
    query: pagingLink(),
  })
}

function refreshPageData({ silent = true } = {}) {
  loadTask({ silent })
  loadLogs({ silent })
  loadResults({ silent })
}

function handleManualRefresh() {
  refreshPageData({ silent: false })
  ElMessage.info('详情与日志已刷新')
}

// ===== 任务操作（静态版 withTaskActionLock 互斥锁 + confirm） =====
async function withTaskActionLock(action) {
  if (taskActionInProgress.value) {
    ElMessage.warning('当前已有任务操作正在执行，请稍候')
    return
  }
  taskActionInProgress.value = true
  try {
    await action()
  } finally {
    taskActionInProgress.value = false
    // 操作完成后静默刷新详情/日志/结果
    refreshPageData()
  }
}

async function handleStopTask() {
  try {
    await ElMessageBox.confirm(
      '确认停止当前回测任务吗？已完成的结果会保留，任务状态会变为已取消。',
      '停止任务',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await withTaskActionLock(async () => {
    try {
      await cancelTask(taskId)
      ElMessage.success('任务已停止')
    } catch (error) {
      ElMessage.error(`停止任务失败：${error.message || '未知错误'}`)
    }
  })
}

async function handleResumeRestartTask() {
  try {
    await ElMessageBox.confirm(
      '确认按断点继续重启当前任务吗？系统会尽量从当前进度恢复执行。',
      '断点重启',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await withTaskActionLock(async () => {
    try {
      await restartTask(taskId, { resume_from_checkpoint: true })
      ElMessage.success('任务已按断点重启')
    } catch (error) {
      ElMessage.error(`断点重启失败：${error.message || '未知错误'}`)
    }
  })
}

async function handleRestartFromScratch() {
  try {
    await ElMessageBox.confirm(
      '确认重头开始当前任务吗？这会清空当前任务已有结果并从第 1 步重新执行。',
      '重头开始',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await withTaskActionLock(async () => {
    try {
      await restartTask(taskId, { resume_from_checkpoint: false })
      ElMessage.success('任务已重头开始')
    } catch (error) {
      ElMessage.error(`重头开始失败：${error.message || '未知错误'}`)
    }
  })
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadTask(), loadLogs()])
    await loadResults()
  } finally {
    loading.value = false
  }
})

// 静态版 60 秒全状态静默轮询（详情 + 日志 + 结果）
usePolling(() => refreshPageData({ silent: true }), { interval: 60000, immediate: false })
</script>

<style scoped>
.backtest-multi-detail-page__metrics {
  margin-bottom: 16px;
}

.backtest-multi-detail-page__hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.backtest-multi-detail-page__hero-stat {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  text-align: center;
}

.backtest-multi-detail-page__hero-value {
  color: #fff;
  font-size: 24px;
  font-weight: 700;
}

.backtest-multi-detail-page__hero-label {
  color: rgba(255, 255, 255, 0.76);
  font-size: 12px;
}

.backtest-multi-detail-page__log-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.backtest-multi-detail-page__log-panel {
  height: 320px;
  overflow-y: auto;
  overflow-x: auto;
  padding: 12px 14px;
  border-radius: 14px;
  background: #0b1220;
  color: #dbeafe;
  font-family: 'Fira Code', monospace;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre;
  word-break: normal;
}

.backtest-multi-detail-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.backtest-multi-detail-page__param-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.backtest-multi-detail-page__param-summary {
  display: grid;
  gap: 4px;
}

.backtest-multi-detail-page__param-main,
.backtest-multi-detail-page__param-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.backtest-multi-detail-page__chip {
  max-width: 100%;
  height: auto;
  padding: 2px 8px;
  white-space: normal;
  word-break: break-all;
}

.backtest-multi-detail-page__config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.backtest-multi-detail-page__config-item {
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
}

.backtest-multi-detail-page__config-label {
  margin-bottom: 4px;
  color: var(--app-text-muted, #94a3b8);
  font-size: 12px;
}

.backtest-multi-detail-page__config-value {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
  word-break: break-all;
}

.backtest-multi-detail-page__modal-subtitle {
  margin-bottom: 8px;
}

.backtest-multi-detail-page__modal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.backtest-multi-detail-page__modal-empty {
  padding: 32px 0;
}

.log-line {
  white-space: pre;
  word-break: normal;
  margin-bottom: 4px;
}

.log-info { color: #93c5fd; }
.log-warning { color: #fcd34d; }
.log-error { color: #fca5a5; }
</style>
