<template>
  <div class="app-page backtest-list-page">
    <PageToolbar
      eyebrow="Backtest Center"
      title="数据回测中心"
      description="集中查看回测任务状态、运行情况和入口操作，快速进入详情或创建新任务。"
    >
      <template #actions>
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
      <el-table-column label="任务名称" min-width="200">
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(`/backtest/${row.id}`)">{{ row.name }}</el-link>
          <div class="inline-muted font-mono">{{ row.id?.slice(0, 8) }}...</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="160">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(`/backtest/${row.id}`)">详情</el-button>
        </template>
      </el-table-column>
    </DataTableCard>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { getTasks } from '@/api/task'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import StatusTag from '@/components/StatusTag.vue'
import { usePolling } from '@/composables/usePolling'

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })

const statCards = [
  { key: 'total', label: '任务总数' },
  { key: 'running', label: '运行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '执行失败' },
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

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, task_type: 'backtest_training' }
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0

    const s = res.statistics || {}
    stats.value = {
      total: s.total_tasks ?? res.pagination?.total ?? 0,
      running: (s.running_tasks ?? 0) + (s.pending_tasks ?? 0),
      completed: s.completed_tasks ?? 0,
      failed: s.error_tasks ?? 0,
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

usePolling(loadTasks, { interval: 30000 })
</script>
