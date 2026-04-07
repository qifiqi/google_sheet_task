<template>
  <div class="app-page task-list-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Queue</div>
        <h2 class="page-title">{{ versionLabel }} 任务列表</h2>
        <p class="page-description">查看任务排队、执行进度和错误状态，支持版本切换、筛选和移动端快速巡检。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button v-if="version === 'c3'" :size="componentSize" @click="$router.push('/task/create/c31')">
          创建批量任务
        </el-button>
        <el-button type="primary" :size="componentSize" @click="$router.push(`/task/create/${version}`)">
          创建新任务
        </el-button>
      </div>
    </div>

    <el-row :gutter="12" class="task-list-stats">
      <el-col v-for="card in statCards" :key="card.key" :xs="12" :sm="6" class="task-list-stats__col">
        <div class="task-stat-card">
          <div class="task-stat-card__label">{{ card.label }}</div>
          <div class="task-stat-card__value">{{ stats[card.key] ?? 0 }}</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="task-filter-card">
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :sm="6" :md="4">
          <el-select v-model="filters.status" placeholder="状态" clearable class="full-width" @change="doFilter">
            <el-option value="pending" label="待执行" />
            <el-option value="running" label="运行中" />
            <el-option value="completed" label="已完成" />
            <el-option value="cancelled" label="已取消" />
            <el-option value="error" label="错误" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="8" :md="6">
          <el-input v-model.trim="filters.keyword" placeholder="任务名称 / ID" clearable @keyup.enter="doFilter" @clear="doFilter" />
        </el-col>
        <el-col :xs="12" :sm="4" :md="2">
          <el-button @click="clearFilters">清空</el-button>
        </el-col>
        <el-col :xs="12" :sm="4" :md="2">
          <el-button @click="loadTasks">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="!isMobile" shadow="never" class="task-table-card">
      <div class="task-table-card__head">
        <div class="task-table-card__title">任务列表</div>
        <div class="task-table-card__meta">{{ paginationInfo }}</div>
      </div>
      <el-table :data="tasks" v-loading="loading" stripe class="task-list-table">
        <el-table-column label="任务名称" min-width="280">
          <template #default="{ row }">
            <div class="task-main-cell">
              <div class="task-main-cell__title-row">
                <el-link type="primary" class="task-main-cell__title" @click="$router.push(`/task/${row.id}`)">{{ row.name }}</el-link>
                <el-tag size="small" effect="plain" class="task-main-cell__version">{{ versionLabel }}</el-tag>
              </div>
              <div v-if="taskTokenName(row)" class="task-main-cell__meta">Token: {{ taskTokenName(row) }}</div>
              <div v-if="row.description" class="task-main-cell__meta">{{ row.description }}</div>
              <div class="task-id">{{ shortTaskId(row.id) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="参数组" width="90" align="center">
          <template #default="{ row }">
            {{ row.config?.parameters?.length ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="220">
          <template #default="{ row }">
            <div class="task-progress-cell">
              <el-progress
                v-if="row.total_steps > 0"
                :percentage="taskProgressPercentage(row)"
                :format="() => `${row.current_step || 0}/${row.total_steps}`"
              />
              <span v-else class="task-empty">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTime(row.start_time || row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTime(row.end_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="task-actions">
              <el-button link type="primary" @click="$router.push(`/task/${row.id}`)">查看</el-button>
              <el-button v-if="row.status === 'running'" link type="warning" @click="handleCancel(row.id)">停止</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div v-else class="task-mobile-list">
      <div v-loading="loading">
        <el-card
          v-for="task in tasks"
          :key="task.id"
          shadow="hover"
          class="task-mobile-card"
          @click="$router.push(`/task/${task.id}`)"
        >
          <div class="task-mobile-card__header">
            <div>
              <div class="task-mobile-card__name">{{ task.name }}</div>
              <div class="task-id">{{ task.id?.slice(0, 8) }}...</div>
            </div>
            <StatusTag :status="task.status" />
          </div>
          <el-progress
            v-if="task.total_steps > 0"
            :percentage="Math.min(100, Math.round(((task.current_step || 0) / task.total_steps) * 100))"
            :format="() => `${task.current_step || 0}/${task.total_steps}`"
            class="task-mobile-card__progress"
          />
          <div class="task-mobile-card__date">{{ task.created_at }}</div>
        </el-card>
        <el-empty v-if="!tasks.length && !loading" description="暂无任务" />
      </div>
    </div>

    <div class="task-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadTasks"
        @size-change="() => { page = 1; loadTasks() }"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, cancelTask } from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const { isMobile, componentSize } = useResponsive()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })
let refreshTimer = null

const version = computed(() => route.query.version || 'c3')
const versionLabel = computed(() => {
  const labelMap = { c3: 'C3', c4: 'C4', c5: 'C5', c31: 'C31' }
  return labelMap[version.value] || version.value.toUpperCase()
})

const taskTypeMap = { c3: 'google_sheet', c4: 'google_sheet_C4', c5: 'google_sheet_C5', c31: 'google_sheet' }

const statCards = [
  { key: 'total', label: '总任务数' },
  { key: 'completed', label: '已完成' },
  { key: 'running', label: '运行中' },
  { key: 'error', label: '错误' },
]

const paginationInfo = computed(() => {
  if (!total.value) return '暂无任务'
  const start = (page.value - 1) * pageSize.value + 1
  const end = Math.min(page.value * pageSize.value, total.value)
  return `显示第 ${start}-${end} 条，共 ${total.value} 条记录`
})

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    const taskType = taskTypeMap[version.value]
    if (taskType) params.task_type = taskType
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0

    const currentPageTasks = res.tasks || []
    stats.value = {
      total: res.pagination?.total || 0,
      completed: currentPageTasks.filter((task) => task.status === 'completed').length,
      running: currentPageTasks.filter((task) => task.status === 'running').length,
      error: currentPageTasks.filter((task) => task.status === 'error').length,
    }
  } finally {
    loading.value = false
  }
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

function shortTaskId(id) {
  if (!id) return '-'
  return id.length > 8 ? `${id.slice(0, 8)}...` : id
}

function taskTokenName(task) {
  return task?.config?.token_name || ''
}

function taskProgressPercentage(task) {
  if (!task?.total_steps) return 0
  return Math.min(100, Math.round(((task.current_step || 0) / task.total_steps) * 100))
}

function formatDateTime(value) {
  if (!value) return '-'
  const normalized = String(value).replace('T', ' ')
  return normalized.length > 19 ? normalized.slice(0, 19) : normalized
}

async function handleCancel(id) {
  await ElMessageBox.confirm('确定要停止这个任务吗？', '确认停止', { type: 'warning' })
  await cancelTask(id)
  ElMessage.success('已发送停止请求')
  loadTasks()
}

onMounted(() => {
  loadTasks()
  refreshTimer = setInterval(loadTasks, 30000)
})

watch(version, () => {
  page.value = 1
  filters.status = ''
  filters.keyword = ''
  loadTasks()
})

onUnmounted(() => clearInterval(refreshTimer))
</script>

<style scoped>
.task-list-hero {
  margin-bottom: 18px;
}

.task-list-stats {
  margin-bottom: 4px;
}

.task-list-stats__col {
  margin-bottom: 12px;
}

.task-stat-card {
  padding: 16px;
  border: 1px solid var(--app-border);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(244, 248, 253, 0.9) 100%);
  box-shadow: var(--app-shadow-soft);
}

.task-stat-card__label {
  color: var(--app-text-muted);
  font-size: 14px;
}

.task-stat-card__value {
  margin-top: 8px;
  color: var(--app-text);
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
}

.task-filter-card {
  margin-bottom: 16px;
}

.task-table-card {
  overflow: hidden;
}

.task-table-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.task-table-card__title {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text);
}

.task-table-card__meta {
  color: var(--app-text-muted);
  font-size: 14px;
}

.task-main-cell__title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.task-main-cell__title {
  font-size: 17px;
  font-weight: 700;
}

.task-main-cell__version {
  font-weight: 700;
}

.task-main-cell__meta {
  margin-top: 4px;
  color: var(--app-text-muted);
  font-size: 14px;
}

.task-id {
  margin-top: 4px;
  color: var(--app-text-muted);
  font-family: 'Fira Code', monospace;
  font-size: 13px;
}

.task-empty {
  color: var(--app-text-muted);
}

.task-progress-cell {
  min-width: 180px;
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.task-mobile-list {
  margin-top: 2px;
}

.task-mobile-card {
  margin-bottom: 12px;
  cursor: pointer;
}

.task-mobile-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.task-mobile-card__name {
  margin-bottom: 4px;
  color: var(--app-text);
  font-weight: 700;
}

.task-mobile-card__date {
  margin-top: 8px;
  color: var(--app-text-muted);
  font-size: 12px;
}

.task-mobile-card__progress {
  margin-top: 10px;
}

.task-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 767px) {
  .task-stat-card {
    padding: 14px;
  }

  .task-stat-card__value {
    font-size: 22px;
  }

  .task-pagination {
    justify-content: center;
  }
}
</style>
