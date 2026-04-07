<template>
  <div class=" backtest-list-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Center</div>
        <h2 class="page-title">数据回测中心</h2>
        <p class="page-description">集中查看回测任务状态、运行情况和入口操作，快速进入详情或创建新任务。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button type="primary" @click="$router.push('/backtest/create')">创建新任务</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="backtest-list-page__metrics">
      <el-col :xs="12" :sm="6" class="backtest-list-page__metric-col">
        <div class="sub-card backtest-list-page__metric-card">
          <div class="panel-note">任务总数</div>
          <div class="backtest-list-page__metric-value">{{ stats.total ?? 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-list-page__metric-col">
        <div class="sub-card backtest-list-page__metric-card">
          <div class="backtest-list-page__metric-label backtest-list-page__metric-label--primary">运行中</div>
          <div class="backtest-list-page__metric-value backtest-list-page__metric-value--primary">
            {{ stats.running ?? 0 }}
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-list-page__metric-col">
        <div class="sub-card backtest-list-page__metric-card">
          <div class="backtest-list-page__metric-label backtest-list-page__metric-label--success">已完成</div>
          <div class="backtest-list-page__metric-value backtest-list-page__metric-value--success">
            {{ stats.completed ?? 0 }}
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6" class="backtest-list-page__metric-col">
        <div class="sub-card backtest-list-page__metric-card">
          <div class="backtest-list-page__metric-label backtest-list-page__metric-label--danger">执行失败</div>
          <div class="backtest-list-page__metric-value backtest-list-page__metric-value--danger">
            {{ stats.failed ?? 0 }}
          </div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">筛选条件</h3>
      </div>
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :sm="6">
          <el-select
            v-model="filters.status"
            placeholder="任务状态"
            clearable
            class="full-width"
            @change="doFilter"
          >
            <el-option value="pending" label="待执行" />
            <el-option value="running" label="运行中" />
            <el-option value="completed" label="已完成" />
            <el-option value="cancelled" label="已取消" />
            <el-option value="error" label="错误" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-input
            v-model="filters.keyword"
            placeholder="任务名称 / ID"
            clearable
            @keyup.enter="doFilter"
            @clear="doFilter"
          />
        </el-col>
        <el-col :xs="12" :sm="3">
          <el-button @click="clearFilters">清空</el-button>
        </el-col>
        <el-col :xs="12" :sm="3">
          <el-button @click="loadTasks">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="page-section">
      <el-table :data="tasks" v-loading="loading" stripe>
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
            <el-progress
              v-if="row.total_steps > 0"
              :percentage="Math.min(100, Math.round(((row.current_step || 0) / row.total_steps) * 100))"
              :format="() => `${row.current_step || 0}/${row.total_steps}`"
            />
            <span v-else class="panel-note">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/backtest/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="backtest-list-page__pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadTasks"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { getTasks } from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })
let refreshTimer = null

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, task_type: 'backtest_training' }
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0

    const currentTasks = res.tasks || []
    stats.value = {
      total: res.pagination?.total || 0,
      running: currentTasks.filter((task) => task.status === 'running' || task.status === 'pending').length,
      completed: currentTasks.filter((task) => task.status === 'completed').length,
      failed: currentTasks.filter((task) => task.status === 'error').length
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

onMounted(() => {
  loadTasks()
  refreshTimer = setInterval(loadTasks, 30000)
})

onUnmounted(() => clearInterval(refreshTimer))
</script>

<style scoped>
.full-width {
  width: 100%;
}

.backtest-list-page__metrics {
  margin-bottom: 4px;
}

.backtest-list-page__metric-col {
  margin-bottom: 12px;
}

.backtest-list-page__metric-card {
  height: 100%;
}

.backtest-list-page__metric-label {
  font-size: 12px;
  font-weight: 600;
}

.backtest-list-page__metric-label--primary,
.backtest-list-page__metric-value--primary {
  color: var(--app-primary);
}

.backtest-list-page__metric-label--success,
.backtest-list-page__metric-value--success {
  color: #16a34a;
}

.backtest-list-page__metric-label--danger,
.backtest-list-page__metric-value--danger {
  color: #dc2626;
}

.backtest-list-page__metric-value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text);
}

.backtest-list-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
