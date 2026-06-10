<template>
  <div class="task-list-page">
    <PageToolbar eyebrow="任务中心" title="任务列表">
      <template #actions>
        <el-dropdown @command="handleCreate">
          <el-button type="primary">
            创建任务 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="c3">C3 参数校验</el-dropdown-item>
              <el-dropdown-item command="c4">C4 参数校验</el-dropdown-item>
              <el-dropdown-item command="c5">C5 参数校验</el-dropdown-item>
              <el-dropdown-item command="c31" divided>C31 批量创建</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </PageToolbar>

    <StatCardGrid
      :cards="STAT_CARDS"
      :data="stats"
      :columns="{ xs: 12, sm: 6, md: 6 }"
      variant="gradient"
      class="mb-4"
    />

    <FilterToolbar
      :filters="FILTERS"
      v-model="filterValues"
      @search="loadTasks"
      @clear="clearFilters"
      class="mb-3"
    />

    <el-table
      :data="tasks"
      v-loading="loading"
      stripe
      style="width: 100%"
      @row-click="goDetail"
    >
      <el-table-column prop="task_name" label="任务名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="task_type" label="类型" width="130" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.task_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" width="160">
        <template #default="{ row }">
          <TaskProgressCell :current="row.current_step" :total="row.total_steps" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="175" align="center">
        <template #default="{ row }">
          <span class="cell-time">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <TaskActions :task="row" @refresh="loadTasks" />
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadTasks"
        @current-change="loadTasks"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { getTasks } from '@/api/task'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import TaskActions from './components/TaskActions.vue'

const router = useRouter()

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filters = ref({ status: '', task_type: '', search: '' })
const filterValues = ref({ status: '', search: '' })

const stats = ref({ total: 0, completed: 0, running: 0, error: 0 })

const STAT_CARDS = [
  { key: 'total', label: '全部任务', background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
  { key: 'completed', label: '已完成', background: 'linear-gradient(135deg, #10b981, #059669)' },
  { key: 'running', label: '运行中', background: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { key: 'error', label: '异常', background: 'linear-gradient(135deg, #ef4444, #dc2626)' },
]

const FILTERS = [
  { key: 'status', type: 'select', label: '状态', options: [
    { label: '全部', value: '' },
    { label: '待执行', value: 'pending' },
    { label: '运行中', value: 'running' },
    { label: '已完成', value: 'completed' },
    { label: '错误', value: 'error' },
    { label: '已取消', value: 'cancelled' },
  ]},
  { key: 'search', type: 'input', label: '搜索', placeholder: '任务名称 / ID' },
]

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function onFilterChange() {
  filters.value = { ...filterValues.value }
  page.value = 1
  loadTasks()
}

function clearFilters() {
  filterValues.value = { status: '', search: '' }
  filters.value = { status: '', task_type: '', search: '' }
  page.value = 1
  loadTasks()
}

async function loadTasks() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: pageSize.value,
      ...filters.value,
    }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })

    const res = await getTasks(params)
    const data = res.data || res
    tasks.value = data.tasks || data.items || data || []
    total.value = data.total || tasks.value.length

    // Compute stats
    const all = tasks.value
    stats.value = {
      total: total.value,
      completed: all.filter(t => t.status === 'completed').length,
      running: all.filter(t => t.status === 'running').length,
      error: all.filter(t => t.status === 'error').length,
    }
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  if (row.task_type?.startsWith('backtest')) {
    router.push(`/backtest/${row.id}`)
  } else {
    router.push(`/task/${row.id}`)
  }
}

function handleCreate(cmd) {
  router.push(`/task/create/${cmd}`)
}

usePolling(loadTasks, { interval: 15000 })
onMounted(loadTasks)
</script>

<style lang="scss" scoped>
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
