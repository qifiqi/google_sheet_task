<template>
  <div class="app-page task-list-page">
    <PageToolbar
      eyebrow="Task Queue"
      :title="`${versionLabel} 任务列表`"
      description="查看任务排队、执行进度和错误状态，支持版本切换、筛选和移动端快速巡检。"
    >
      <template #actions>
        <el-button v-if="version === 'c3'" :size="componentSize" @click="$router.push('/task/create/c31')">
          创建批量任务
        </el-button>
        <el-button type="primary" :size="componentSize" @click="$router.push(`/task/create/${version}`)">
          创建新任务
        </el-button>
      </template>
    </PageToolbar>

    <StatCardGrid :cards="statCards" :data="stats" :columns="{ xs: 12, sm: 6, md: 6 }" />

    <FilterToolbar
      v-model="filters"
      :filters="filterDefs"
      @search="doFilter"
      @clear="clearFilters"
    />

    <DataTableCard
      v-if="!isMobile"
      title="任务列表"
      :loading="loading"
      :data="tasks"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      @page-change="loadTasks"
    >
      <template #header-extra>{{ paginationInfo }}</template>

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
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
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
    </DataTableCard>

    <MobileCardList v-else :data="tasks" :loading="loading" @item-click="(task) => $router.push(`/task/${task.id}`)">
      <template #card="{ item: task }">
        <el-card shadow="hover" class="task-mobile-card">
          <div class="task-mobile-card__header">
            <div>
              <div class="task-mobile-card__name">{{ task.name }}</div>
              <div class="task-id">{{ task.id?.slice(0, 8) }}...</div>
            </div>
            <StatusTag :status="task.status" />
          </div>
          <TaskProgressCell
            v-if="task.total_steps > 0"
            :current-step="task.current_step || 0"
            :total-steps="task.total_steps"
            class="task-mobile-card__progress"
          />
          <div class="task-mobile-card__date">{{ task.created_at }}</div>
        </el-card>
      </template>
    </MobileCardList>

    <div class="task-pagination">
      <el-pagination
        v-if="isMobile"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadTasks"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, cancelTask } from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import MobileCardList from '@/components/MobileCardList.vue'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const route = useRoute()
const { isMobile, componentSize } = useResponsive()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })

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

const filterDefs = [
  {
    key: 'status',
    type: 'select',
    placeholder: '状态',
    span: { xs: 24, sm: 6, md: 4 },
    options: [
      { value: 'pending', label: '待执行' },
      { value: 'running', label: '运行中' },
      { value: 'completed', label: '已完成' },
      { value: 'cancelled', label: '已取消' },
      { value: 'error', label: '错误' },
    ],
  },
  { key: 'keyword', type: 'input', placeholder: '任务名称 / ID', span: { xs: 24, sm: 8, md: 6 } },
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

usePolling(loadTasks, { interval: 30000 })

watch(version, () => {
  page.value = 1
  filters.status = ''
  filters.keyword = ''
  loadTasks()
})
</script>

<style scoped>
.task-list-stats {
  margin-bottom: 4px;
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

.task-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.task-mobile-card {
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
  .task-pagination {
    justify-content: center;
  }
}
</style>
