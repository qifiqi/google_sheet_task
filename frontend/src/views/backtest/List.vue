<template>
  <div class="app-page backtest-list-page">
    <PageToolbar
      eyebrow="Backtest Center"
      title="数据回测中心"
      description="统一查看与管理 C3 / C5 回测任务，实时追踪任务执行状态。"
    >
      <template #actions>
        <span class="inline-muted backtest-list-page__refresh">最后刷新：{{ lastUpdated || '-' }}</span>
        <el-button type="success" plain @click="openBatchExportDialog">批量导出</el-button>
        <el-button type="primary" @click="$router.push('/backtest/create')">创建新任务</el-button>
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
      <el-table-column label="任务名称" min-width="220">
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(detailRoute(row))">{{ row.name || '未命名任务' }}</el-link>
          <div class="inline-muted font-mono">ID: {{ row.id?.slice(0, 8) }} · Sheet: {{ getSheetName(row) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="模型版本" width="100">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ inferModelVersion(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="K线范围" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">
          {{ buildKlineRangeText(row) }}
        </template>
      </el-table-column>
      <el-table-column label="执行参数" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ buildExecutionParamsText(row) || '-' }}
        </template>
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
          {{ row.start_time ? formatDateTime(row.start_time) : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="结束时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.end_time ? formatDateTime(row.end_time) : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(detailRoute(row))">详情</el-button>
          <el-button link type="danger" @click="handleDeleteTask(row)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <el-dialog v-model="batchExportDialogVisible" title="批量导出当前页任务" width="720px" top="6vh">
      <div class="panel-note" style="margin-bottom: 12px;">已完成任务可选，导出为 ZIP。</div>
      <div class="backtest-list-page__batch-summary">
        <div class="backtest-list-page__batch-count">
          当前页 {{ tasks.length }} 个任务，可导出 {{ exportableTasks.length }} 个，已选 {{ selectedBatchCount }} 个
        </div>
        <div class="control-row">
          <el-button size="small" @click="selectAllExportableTasks">全选当前页</el-button>
          <el-button size="small" @click="selectAllExportableTasks">仅已完成任务</el-button>
          <el-button size="small" @click="clearBatchExportSelection">清空</el-button>
        </div>
      </div>

      <div class="backtest-list-page__batch-list">
        <div v-if="!tasks.length" class="panel-note panel-note--center">当前页暂无可展示任务</div>
        <div
          v-for="task in tasks"
          :key="task.id"
          :class="['backtest-list-page__batch-card', {
            'is-selected': selectedBatchExportTaskIds.has(String(task.id)),
            'is-disabled': task.status !== 'completed',
          }]"
          :role="task.status === 'completed' ? 'button' : undefined"
          @click="toggleBatchExportTask(task)"
        >
          <el-checkbox
            :model-value="selectedBatchExportTaskIds.has(String(task.id))"
            :disabled="task.status !== 'completed'"
            @click.prevent
          />
          <div class="backtest-list-page__batch-info">
            <div class="backtest-list-page__batch-title">{{ task.name || '未命名任务' }}</div>
            <div class="panel-note">ID: {{ String(task.id || '').slice(0, 8) }} · Sheet: {{ getSheetName(task) }}</div>
            <div class="panel-note">模型版本：{{ inferModelVersion(task) }} · 创建：{{ formatDateTime(task.created_at) }}</div>
            <div v-if="task.status !== 'completed'" class="panel-note">尚未完成，不可导出</div>
          </div>
          <StatusTag :status="task.status" />
        </div>
      </div>

      <template #footer>
        <div class="backtest-list-page__batch-footer">
          <span class="panel-note">ZIP 内每个任务保留原全局预览 XLSX 格式。</span>
          <div>
            <el-button @click="batchExportDialogVisible = false">取消</el-button>
            <el-button
              type="success"
              :disabled="selectedBatchCount < 1"
              :loading="batchExporting"
              @click="exportSelectedBatchTasks"
            >导出 ZIP</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getTasks, deleteTask } from '@/api/task'
import { exportGlobalPreviewsBatch } from '@/api/backtest'
import { initialListPagination, writeJsonStorage, replaceQuery } from '@/utils/pageState'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import StatusTag from '@/components/StatusTag.vue'
import { usePolling } from '@/composables/usePolling'

const route = useRoute()
const router = useRouter()
const LIST_KEY = 'backtest_training:list_pagination'
const initialPagination = initialListPagination(route.query, LIST_KEY, 20)
const tasks = ref([])
const loading = ref(false)
const page = ref(initialPagination.page)
const pageSize = ref(initialPagination.perPage)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })
const lastUpdated = ref('')

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
]

// ---------- 任务配置解析（config 可能因历史数据为 JSON 字符串） ----------
function parseTaskConfig(task) {
  const config = task?.config
  if (config && typeof config === 'object') return config
  if (typeof config === 'string' && config) {
    try {
      return JSON.parse(config)
    } catch {
      return {}
    }
  }
  return {}
}

function getSheetName(task) {
  const config = parseTaskConfig(task)
  return config?.sheet?.sheet_name || '-'
}

// 模型版本推断（翻译自静态 inferModelVersion：标题子版本号一并展示）
function inferModelVersion(task) {
  if (task?.model_version) {
    return String(task.model_version).toUpperCase()
  }
  const config = parseTaskConfig(task)
  const sheet = config.sheet || {}
  const title = String(sheet.title || config.title || task?.name || '').toUpperCase()
  if (title.includes('C7.0.3')) return 'C7.0.3'
  if (title.includes('C7')) return 'C7'
  if (title.includes('C5')) return 'C5'
  if (title.includes('C4')) return 'C4'
  if (title.includes('C3') || title.includes('CHARTING:3')) return 'C3'

  const parameters = Array.isArray(config.parameters) ? config.parameters : []
  const firstRow = Array.isArray(parameters[0]) ? parameters[0] : []
  if (firstRow.length === 2) return 'C5'
  if (firstRow.length >= 7) return 'C3'
  return '-'
}

function buildKlineRangeText(task) {
  const config = parseTaskConfig(task)
  const endDate = config.end_date || ''
  const fullYears = Array.isArray(config.full_years) ? config.full_years.filter(Boolean) : []
  if (fullYears.length) {
    const earliestYear = Math.min(...fullYears.map((year) => Number(year) || 0))
    return `${earliestYear}-01-01 ~ ${endDate || '运行日前一日'}`
  }
  if (config.recent_years) {
    return `近 ${config.recent_years} 年 · 截至 ${endDate || '运行日'}`
  }
  return endDate ? `截至 ${endDate}` : '-'
}

// 执行参数去重：完全相同的参数行只展示一次。
function buildExecutionParamsText(task) {
  const config = parseTaskConfig(task)
  const rows = Array.isArray(config.parameters) ? config.parameters : []
  const seen = new Set()
  const uniqueRows = []
  rows.forEach((row) => {
    const key = JSON.stringify(row)
    if (seen.has(key)) {
      return
    }
    seen.add(key)
    uniqueRows.push((Array.isArray(row) ? row : [row]).join('/'))
  })
  return uniqueRows.join('；')
}

// ---------- 列表加载 ----------
async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, task_type: 'backtest_training' }
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.items || []
    total.value = res.total || 0

    // 分页状态落 localStorage + URL（与静态版 persistListPaginationState 一致）
    writeJsonStorage(LIST_KEY, { page: page.value, per_page: pageSize.value })
    replaceQuery(router, route, { page: String(page.value), per_page: String(pageSize.value) })

    const s = res.statistics || {}
    stats.value = {
      total: s.total_tasks ?? res.total ?? 0,
      running: s.running_tasks ?? 0,
      completed: s.completed_tasks ?? 0,
      failed: s.error_tasks ?? 0,
    }
    lastUpdated.value = formatDateTime(new Date().toISOString())
  } finally {
    loading.value = false
  }
}

function detailRoute(row) {
  return { path: `/backtest/${row.id}`, query: { list_page: String(page.value), list_per_page: String(pageSize.value) } }
}

function doFilter() {
  page.value = 1
  loadTasks()
}

function clearFilters() {
  filters.status = ''
  filters.keyword = ''
  doFilter()
}

// ---------- 行内删除 ----------
async function handleDeleteTask(row) {
  try {
    await ElMessageBox.confirm(`确认删除任务 ${row.id} 吗？`, '确认删除', { type: 'warning' })
  } catch {
    return
  }

  try {
    await deleteTask(row.id)
    ElMessage.success('任务已删除')
    // 末页最后一条删除后回退页码（与静态版 deleteTask 行为一致）
    const isLastPageOnlyRow = total.value > 1 && page.value > 1 && tasks.value.length <= 1
    if (isLastPageOnlyRow) {
      page.value -= 1
    }
    await loadTasks()
  } catch (error) {
    ElMessage.error(`删除失败：${error.message || '未知错误'}`)
  }
}

// ---------- 批量导出 ----------
const batchExportDialogVisible = ref(false)
const batchExporting = ref(false)
const selectedBatchExportTaskIds = ref(new Set())

const exportableTasks = computed(() => tasks.value.filter((task) => task.status === 'completed'))
const selectedBatchCount = computed(() => selectedBatchExportTaskIds.value.size)

function openBatchExportDialog() {
  pruneBatchExportSelection()
  batchExportDialogVisible.value = true
}

function pruneBatchExportSelection() {
  const knownIds = new Set(tasks.value.map((task) => String(task.id || '')))
  const next = new Set([...selectedBatchExportTaskIds.value].filter((taskId) => knownIds.has(taskId)))
  selectedBatchExportTaskIds.value = next
}

function toggleBatchExportTask(task) {
  if (task.status !== 'completed') {
    return
  }
  const taskId = String(task.id || '')
  const next = new Set(selectedBatchExportTaskIds.value)
  if (next.has(taskId)) {
    next.delete(taskId)
  } else {
    next.add(taskId)
  }
  selectedBatchExportTaskIds.value = next
}

function selectAllExportableTasks() {
  selectedBatchExportTaskIds.value = new Set(exportableTasks.value.map((task) => String(task.id)))
}

function clearBatchExportSelection() {
  selectedBatchExportTaskIds.value = new Set()
}

async function exportSelectedBatchTasks() {
  const taskIds = [...selectedBatchExportTaskIds.value]
  if (!taskIds.length) {
    return
  }

  batchExporting.value = true
  try {
    const { blob, filename } = await exportGlobalPreviewsBatch(taskIds)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    batchExportDialogVisible.value = false
    ElMessage.success(`已开始下载：${filename}`)
  } catch (error) {
    ElMessage.error(error.message || '导出失败')
  } finally {
    batchExporting.value = false
  }
}

usePolling(loadTasks, { interval: 5000 })
</script>

<style scoped>
.backtest-list-page__refresh {
  margin-right: 8px;
}

.backtest-list-page__batch-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: rgba(232, 239, 250, 0.5);
}

.backtest-list-page__batch-count {
  font-weight: 700;
}

.backtest-list-page__batch-list {
  max-height: 52vh;
  display: grid;
  gap: 8px;
  overflow-y: auto;
}

.backtest-list-page__batch-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  cursor: pointer;
}

.backtest-list-page__batch-card.is-selected {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.06);
}

.backtest-list-page__batch-card.is-disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.backtest-list-page__batch-info {
  flex: 1;
  display: grid;
  gap: 2px;
}

.backtest-list-page__batch-title {
  font-weight: 700;
  color: var(--app-text);
}

.backtest-list-page__batch-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
</style>
