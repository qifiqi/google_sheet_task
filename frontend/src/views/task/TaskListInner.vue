<template>
  <div class="app-page task-list-inner">
    <PageToolbar
      :eyebrow="'TASK QUEUE'"
      :title="`${versionLabel} 任务列表`"
      description="查看任务排队、执行进度和错误状态，支持版本切换、筛选和移动端快速巡检。"
    >
      <template #actions>
        <el-button v-if="version === 'c3'" @click="$router.push('/task/create/c31')">
          创建批量任务
        </el-button>
        <el-button type="primary" @click="$router.push(`/task/create/${version}`)">
          创建新任务
        </el-button>
      </template>
    </PageToolbar>

    <StatCardGrid :cards="statCards" :data="stats" class="page-section" />

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
      @page-change="loadTasks"
    >
      <el-table-column label="任务名称" min-width="260">
        <template #default="{ row }">
          <div class="task-cell__title-row">
            <a class="task-cell__name" @click="router.push(`/task/${row.id}`)">{{ row.name }}</a>
            <el-tag size="small" type="info" effect="plain">{{ versionLabel }}</el-tag>
          </div>
          <div v-if="row.config?.token_name" class="task-cell__meta">Token: {{ row.config.token_name }}</div>
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
      <el-table-column label="操作" width="130" fixed="right" align="center">
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
          <TaskProgressCell
            v-if="task.total_steps"
            :current-step="task.current_step || 0"
            :total-steps="task.total_steps || 0"
            class="task-card__progress"
          />
          <div class="task-card__footer">
            <span class="task-card__time">{{ formatDateTime(task.start_time || task.created_at) }}</span>
            <el-button
              v-if="task.status === 'running'"
              link
              type="warning"
              size="small"
              @click.stop="handleCancel(task.id)"
            >
              停止
            </el-button>
          </div>
        </div>
      </div>
      <div class="task-list-inner__pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="prev, pager, next"
          @current-change="loadTasks"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTasks, cancelTask } from '@/api/task'
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

const version = computed(() => route.query.version || 'c3')
const versionLabel = computed(() => {
  const labelMap = { c3: 'C3', c4: 'C4', c5: 'C5', c7: 'C7', c31: 'C31' }
  return labelMap[version.value] || version.value.toUpperCase()
})

const taskTypeMap = { c3: 'google_sheet', c4: 'google_sheet_C4', c5: 'google_sheet_C5', c7: 'google_sheet_C7', c31: 'google_sheet' }

const statCards = [
  { key: 'total', label: '总任务数', color: '#2563eb' },
  { key: 'completed', label: '已完成', color: '#16a34a' },
  { key: 'running', label: '运行中', color: '#f59e0b' },
  { key: 'error', label: '错误', color: '#ef4444' },
]

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

function handlePageSizeChange() {
  page.value = 1
  loadTasks()
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
    .catch(() => {})
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
