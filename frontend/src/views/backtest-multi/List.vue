<template>
  <div class="backtest-multi-list-page">
    <PageToolbar eyebrow="多产品回测" title="回测列表">
      <template #actions>
        <el-button type="primary" @click="router.push('/backtest-multi/create')">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>创建回测
        </el-button>
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
      @search="onSearch"
      @clear="onClear"
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
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" width="160">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step" :total-steps="row.total_steps" />
        </template>
      </el-table-column>
      <el-table-column prop="market_type" label="市场" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.market_type || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="175" align="center">
        <template #default="{ row }">
          <span class="cell-time">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right" align="center">
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
import { Plus } from '@element-plus/icons-vue'
import { getTasks } from '@/api/task'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import TaskActions from '@/views/task/components/TaskActions.vue'

const router = useRouter()

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filterValues = ref({ status: '', search: '' })

const stats = ref({ total: 0, completed: 0, running: 0, error: 0 })

const STAT_CARDS = [
  { key: 'total',     label: '全部回测', background: 'linear-gradient(135deg, #8b5cf6, #6d28d9)' },
  { key: 'completed', label: '已完成',   background: 'linear-gradient(135deg, #10b981, #059669)' },
  { key: 'running',   label: '运行中',   background: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { key: 'error',     label: '异常',     background: 'linear-gradient(135deg, #ef4444, #dc2626)' },
]

const FILTERS = [
  {
    key: 'status', type: 'select', label: '状态',
    options: [
      { label: '全部',   value: '' },
      { label: '待执行', value: 'pending' },
      { label: '运行中', value: 'running' },
      { label: '已完成', value: 'completed' },
      { label: '错误',   value: 'error' },
      { label: '已取消', value: 'cancelled' },
    ],
  },
  { key: 'search', type: 'input', label: '搜索', placeholder: '任务名称 / ID' },
]

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function onSearch() {
  page.value = 1
  loadTasks()
}

function onClear() {
  filterValues.value = { status: '', search: '' }
  page.value = 1
  loadTasks()
}

async function loadTasks() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: pageSize.value,
      task_type: 'backtest_multi_product',
      ...filterValues.value,
    }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
    params.task_type = 'backtest_multi_product'

    const res = await getTasks(params)
    const data = res.data || res
    tasks.value = data.tasks || data.items || data || []
    total.value = data.total || tasks.value.length

    stats.value = {
      total: total.value,
      completed: tasks.value.filter(t => t.status === 'completed').length,
      running:   tasks.value.filter(t => t.status === 'running').length,
      error:     tasks.value.filter(t => t.status === 'error').length,
    }
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  router.push(`/backtest-multi/${row.id}`)
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
