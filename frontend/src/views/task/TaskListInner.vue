<template>
  <div class="app-page task-list-inner">
    <PageToolbar
      :eyebrow="'TASK QUEUE'"
      :title="`${versionLabel} 任务列表`"
      description="查看任务排队、执行进度和错误状态，支持版本切换、筛选和移动端快速巡检。"
    >
      <template #actions>
        <el-button v-if="version === 'c3'" @click="$router.push('/task/merge-export')">
          合并导出
        </el-button>
        <el-button v-if="version === 'c3'" @click="$router.push('/task/create/c31')">
          创建批量任务
        </el-button>
        <el-button type="primary" @click="$router.push(`/task/create/${version}`)">
          创建新任务
        </el-button>
      </template>
    </PageToolbar>

    <!-- 统计卡：主数 + 进度条 + 子指标（对齐静态版 google_sheet_index.js updateStatisticsFromServer） -->
    <StatCardGrid :cards="statCards" :data="stats" class="page-section">
      <template #card="{ card, value }">
        <div class="task-stat-card" :style="{ '--accent': card.color || 'var(--app-primary)' }">
          <div class="task-stat-card__label">{{ card.label }}</div>
          <div class="task-stat-card__value">{{ value ?? 0 }}</div>
          <el-progress
            class="task-stat-card__progress"
            :percentage="card.progress"
            :stroke-width="4"
            :show-text="false"
            :color="card.color"
          />
          <div class="task-stat-card__hint">{{ card.hint }}</div>
        </div>
      </template>
    </StatCardGrid>

    <!-- 待重启任务提醒（对齐静态版 checkPendingTasks / checkAllPendingTasks） -->
    <el-alert
      v-if="pendingAlertVisible"
      type="warning"
      show-icon
      class="page-section task-list-inner__pending-alert"
      @close="pendingAlertDismissed = true"
    >
      <template #title>
        检测到 {{ stats.pending_tasks || 0 }} 个任务可能因应用重启而中断，建议检查并重新启动。
      </template>
      <el-button size="small" type="warning" plain @click="viewPendingTasks">查看详情</el-button>
      <el-button v-if="previousPendingView" size="small" @click="restorePreviousView">
        返回原视图
      </el-button>
    </el-alert>

    <FilterToolbar v-model="filters" :filters="filterDefs" @search="doFilter" @clear="clearFilters" />

    <!-- 桌面表格 -->
    <DataTableCard
      v-if="!isMobile"
      title="任务列表"
      :data="tasks"
      :loading="loading"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :page-sizes="[5, 10, 20, 50, 100]"
      @page-change="loadTasks"
    >
      <el-table-column label="任务名称" min-width="260">
        <template #default="{ row }">
          <div class="task-cell__title-row">
            <a class="task-cell__name" @click="router.push(`/task/${row.id}`)">{{ row.name }}</a>
            <el-tag size="small" type="info" effect="plain">{{ versionLabel }}</el-tag>
          </div>
          <div v-if="row.config?.token_name" class="task-cell__meta">Token: {{ row.config.token_name }}</div>
          <div v-if="row.description" class="task-cell__meta">{{ row.description }}</div>
          <div class="task-cell__id">{{ shortTaskId(row.id) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96" align="center">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="180">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column label="开始时间" width="170">
        <template #default="{ row }">
          <span class="task-cell__time">{{ formatDateTime(row.start_time || row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结束时间" width="170">
        <template #default="{ row }">
          <span class="task-cell__time">{{ formatDateTime(row.end_time) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="router.push(`/task/${row.id}`)">查看</el-button>
          <el-button
            v-if="row.status === 'running'"
            link
            type="warning"
            size="small"
            @click="handleCancel(row.id)"
          >
            停止
          </el-button>
          <!-- 对齐静态版：仅 completed/error 状态提供删除入口 -->
          <el-button
            v-if="row.status === 'completed' || row.status === 'error'"
            link
            type="danger"
            size="small"
            @click="handleDelete(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <!-- 移动端卡片 -->
    <el-card v-if="isMobile" shadow="never" v-loading="loading">
      <el-empty v-if="!tasks.length" description="暂无任务" />
      <div v-else class="task-list-inner__cards">
        <div v-for="task in tasks" :key="task.id" class="task-card" @click="router.push(`/task/${task.id}`)">
          <div class="task-card__header">
            <span class="task-card__name">{{ task.name }}</span>
            <StatusTag :status="task.status" />
          </div>
          <div v-if="task.config?.token_name" class="task-card__meta">
            Token: {{ task.config.token_name }}
          </div>
          <div v-if="task.description" class="task-card__meta">{{ task.description }}</div>
          <TaskProgressCell
            v-if="task.total_steps"
            :current-step="task.current_step || 0"
            :total-steps="task.total_steps || 0"
            class="task-card__progress"
          />
          <div class="task-card__footer">
            <span class="task-card__time">{{ formatDateTime(task.start_time || task.created_at) }}</span>
            <span class="task-card__actions">
              <el-button
                v-if="task.status === 'running'"
                link
                type="warning"
                size="small"
                @click.stop="handleCancel(task.id)"
              >
                停止
              </el-button>
              <el-button
                v-if="task.status === 'completed' || task.status === 'error'"
                link
                type="danger"
                size="small"
                @click.stop="handleDelete(task.id)"
              >
                删除
              </el-button>
            </span>
          </div>
        </div>
      </div>
      <div class="task-list-inner__pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[5, 10, 20, 50, 100]"
          layout="prev, pager, next"
          @current-change="loadTasks"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, cancelTask, deleteTask } from '@/api/task'
import { getConfig } from '@/api/config'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import { formatDateTime } from '@/utils/format'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })
// 待重启提醒：dismissed 后本轮页面生命周期内不再弹出；previousPendingView 记录进入 pending 视图前的浏览上下文
const pendingAlertDismissed = ref(false)
const previousPendingView = ref(null)
// 轮询间隔：读配置 frontend_polling_interval，读不到用静态版默认 15000
const pollingInterval = ref(15000)

const version = computed(() => route.query.version || 'c3')
const versionLabel = computed(() => {
  const labelMap = { c3: 'C3', c4: 'C4', c5: 'C5', c7: 'C7', c31: 'C31' }
  return labelMap[version.value] || version.value.toUpperCase()
})

const taskTypeMap = { c3: 'google_sheet', c4: 'google_sheet_C4', c5: 'google_sheet_C5', c7: 'google_sheet_C7', c31: 'google_sheet' }

const pendingAlertVisible = computed(() => (stats.value.pending_tasks || 0) > 0 && !pendingAlertDismissed.value)

// 进度条语义逐值对齐静态版 updateProgressBars
function clampProgress(value) {
  return Math.min(Math.max(value, 0), 100)
}

// 平均时长格式化：>60 分钟显示 x小时y分钟（对齐静态版 updateStatisticsFromServer）
function formatAvgDuration(avg) {
  const minutes = avg || 0
  return minutes > 60 ? `${Math.round(minutes / 60)}小时${minutes % 60}分钟` : `${minutes}分钟`
}

const statCards = computed(() => {
  const s = stats.value
  const totalTasks = s.total || 0
  const completed = s.completed || 0
  const running = s.running || 0
  const error = s.error || 0
  return [
    {
      key: 'total',
      label: '总任务数',
      color: '#2563eb',
      progress: clampProgress(totalTasks > 0 ? (completed / totalTasks) * 100 : 0),
      hint: `今日新增: ${s.today_new_tasks ?? 0}`,
    },
    {
      key: 'completed',
      label: '已完成',
      color: '#16a34a',
      progress: clampProgress(completed + error > 0 ? (completed / (completed + error)) * 100 : 0),
      hint: `成功率: ${s.success_rate ?? 0}%`,
    },
    {
      key: 'running',
      label: '运行中',
      color: '#f59e0b',
      progress: clampProgress(totalTasks > 0 ? (running / totalTasks) * 100 : 0),
      hint: `平均时长: ${formatAvgDuration(s.avg_duration_minutes)}`,
    },
    {
      key: 'error',
      label: '错误',
      color: '#ef4444',
      progress: clampProgress(totalTasks > 0 ? (error / totalTasks) * 100 : 0),
      hint: `错误率: ${s.error_rate ?? 0}%`,
    },
  ]
})

const filterDefs = [
  {
    key: 'status',
    type: 'select',
    placeholder: '状态筛选',
    options: [
      { value: 'pending', label: '待执行' },
      { value: 'running', label: '运行中' },
      { value: 'completed', label: '已完成' },
      { value: 'cancelled', label: '已取消' },
      { value: 'error', label: '错误' },
    ],
  },
  { key: 'keyword', type: 'input', placeholder: '任务名称 / ID' },
]

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    const taskType = taskTypeMap[version.value]
    if (taskType) params.task_type = taskType
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.items || []
    total.value = res.total || 0

    const s = res.statistics || {}
    stats.value = {
      total: s.total_tasks ?? res.total ?? 0,
      completed: s.completed_tasks ?? 0,
      running: s.running_tasks ?? 0,
      error: s.error_tasks ?? 0,
      pending_tasks: s.pending_tasks ?? 0,
      today_new_tasks: s.today_new_tasks ?? 0,
      success_rate: s.success_rate ?? 0,
      error_rate: s.error_rate ?? 0,
      avg_duration_minutes: s.avg_duration_minutes ?? 0,
    }
  } finally {
    loading.value = false
  }
}

function doFilter() {
  page.value = 1
  loadTasks()
  syncUrl()
}

function clearFilters() {
  filters.status = ''
  filters.keyword = ''
  doFilter()
}

function handlePageSizeChange() {
  page.value = 1
  // 每页数记忆（对齐静态版 changePageSize -> localStorage['tasksPerPage']）
  try {
    localStorage.setItem('tasksPerPage', String(pageSize.value))
  } catch {}
  loadTasks()
  syncUrl()
}

function shortTaskId(id) {
  if (!id) return '-'
  return id.length > 8 ? `${id.slice(0, 8)}...` : id
}

function handleCancel(id) {
  ElMessageBox.confirm('确定要停止这个任务吗？', '确认停止', {
    confirmButtonText: '停止',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      await cancelTask(id)
      ElMessage.success('已发送停止请求')
      loadTasks()
    })
    .catch((e) => {
      if (e === 'cancel' || e === 'close') return
      ElMessage.error(`停止任务失败: ${e?.message || '未知错误'}`)
    })
}

// 删除任务（对齐静态版 deleteTask：仅 completed/error 入口，二次确认后删除并刷新）
function handleDelete(id) {
  ElMessageBox.confirm('确定要删除这个任务吗？删除后无法恢复！', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      await deleteTask(id)
      ElMessage.success('任务已删除')
      loadTasks()
    })
    .catch((e) => {
      if (e === 'cancel' || e === 'close') return
      ElMessage.error(`删除任务失败: ${e?.message || '未知错误'}`)
    })
}

// ── 待重启提醒（对齐静态版 checkPendingTasks / checkAllPendingTasks / restorePreviousView）──

function viewPendingTasks() {
  previousPendingView.value = { status: filters.status, page: page.value }
  pendingAlertDismissed.value = true
  filters.status = 'pending'
  page.value = 1
  loadTasks()
  syncUrl()
  ElMessage.info('已筛选出所有待处理的任务（点击筛选下拉框可切换回其他视图）')
}

function restorePreviousView() {
  if (!previousPendingView.value) return
  filters.status = previousPendingView.value.status
  page.value = previousPendingView.value.page
  previousPendingView.value = null
  loadTasks()
  syncUrl()
}

// ── URL 状态同步：page/filter 写入 query，浏览器前进/后退可恢复（对齐静态版 updateUrl / popstate）──

const URL_FILTERS = ['all', 'running', 'completed', 'error', 'cancelled', 'pending']

function syncUrl() {
  const query = { ...route.query }
  query.page = String(page.value)
  query.filter = filters.status || 'all'
  router.replace({ query })
}

function loadStateFromUrl() {
  const p = parseInt(route.query.page, 10)
  if (!Number.isNaN(p) && p > 0) page.value = p
  const filter = route.query.filter
  if (filter && URL_FILTERS.includes(filter)) {
    filters.status = filter === 'all' ? '' : filter
  }
}

watch(
  () => route.query,
  (q) => {
    // 自身 replace 引起的 query 变化与本地状态一致，early return 避免重复加载
    const p = parseInt(q.page, 10)
    const targetPage = !Number.isNaN(p) && p > 0 ? p : 1
    const targetStatus = URL_FILTERS.includes(q.filter) && q.filter !== 'all' ? q.filter : ''
    if (targetPage === page.value && targetStatus === filters.status) return
    page.value = targetPage
    filters.status = targetStatus
    loadTasks()
  }
)

// 每页数记忆恢复（对齐静态版 restoreUserPreferences）
function restoreUserPreferences() {
  try {
    const savedPageSize = parseInt(localStorage.getItem('tasksPerPage'), 10)
    if ([5, 10, 20, 50, 100].includes(savedPageSize)) pageSize.value = savedPageSize
  } catch {}
}

// 轮询：usePolling 的间隔在启动时固定，读取配置后若不同则停用内置定时器、按配置间隔自建
const poller = usePolling(loadTasks, { interval: pollingInterval.value, immediate: false })
let customPollTimer = null

watch(version, () => {
  page.value = 1
  filters.status = ''
  filters.keyword = ''
  previousPendingView.value = null
  loadTasks()
  syncUrl()
})

onMounted(async () => {
  restoreUserPreferences()
  loadStateFromUrl()
  await loadTasks()
  try {
    const res = await getConfig()
    const interval = Number(res?.config?.frontend_polling_interval)
    if (Number.isFinite(interval) && interval > 0 && interval !== pollingInterval.value) {
      pollingInterval.value = interval
      poller.stop()
      customPollTimer = window.setInterval(() => poller.tick(), interval)
    }
  } catch {}
})

onUnmounted(() => {
  if (customPollTimer) {
    window.clearInterval(customPollTimer)
    customPollTimer = null
  }
})
</script>

<style scoped>
.task-list-inner__pending-alert {
  margin-bottom: 4px;
}

/* 统计卡子指标 + 进度条（StatCardGrid 默认样式在子组件作用域内，这里按静态版卡片结构重写） */
.task-stat-card {
  position: relative;
  padding: 14px 16px 14px 20px;
  border-radius: var(--el-border-radius-base);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  overflow: hidden;
  transition: box-shadow 0.2s;
}

.task-stat-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--accent);
}

.task-stat-card:hover {
  box-shadow: var(--app-shadow-soft);
}

.task-stat-card__label {
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
  margin-bottom: 4px;
}

.task-stat-card__value {
  font-size: 26px;
  font-weight: 700;
  color: var(--app-text);
  line-height: 1.2;
}

.task-stat-card__progress {
  margin-top: 6px;
}

.task-stat-card__hint {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-top: 4px;
}

.task-cell__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-cell__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  cursor: pointer;
  transition: color 0.15s;
}

.task-cell__name:hover {
  color: var(--app-primary);
  text-decoration: underline;
}

.task-cell__meta {
  margin-top: 3px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.task-cell__id {
  margin-top: 2px;
  font-size: 11px;
  color: var(--app-text-soft);
  font-family: 'Fira Code', monospace;
}

.task-cell__time {
  font-size: 13px;
  color: var(--app-text-muted);
  font-family: 'Fira Code', monospace;
}

.task-list-inner__cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-card {
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  cursor: pointer;
  transition: border-color 0.2s;
}

.task-card:active {
  border-color: rgba(99, 102, 241, 0.4);
}

.task-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.task-card__meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.task-card__progress {
  margin-top: 10px;
}

.task-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.task-card__actions {
  display: inline-flex;
  align-items: center;
}

.task-card__time {
  font-size: 12px;
  color: var(--app-text-soft);
  font-family: 'Fira Code', monospace;
}

.task-list-inner__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
