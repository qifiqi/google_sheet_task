<template>
  <div class="admin-dashboard">
    <PageToolbar eyebrow="管理中心" title="仪表盘" description="系统运行状态概览" />

    <StatCardGrid
      :cards="STAT_CARDS"
      :data="stats"
      :columns="{ xs: 12, sm: 6, md: 6 }"
      variant="gradient"
      class="mb-4"
    />

    <el-row :gutter="16" class="mb-4">
      <el-col :xs="24" :sm="24" :md="8">
        <el-card shadow="never">
          <template #header>任务趋势</template>
          <ChartPanel :loading="chartLoading">
            <canvas ref="trendChartRef" />
          </ChartPanel>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8">
        <el-card shadow="never">
          <template #header>状态分布</template>
          <ChartPanel :loading="chartLoading">
            <canvas ref="statusChartRef" />
          </ChartPanel>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8">
        <el-card shadow="never">
          <template #header>类型分布</template>
          <ChartPanel :loading="chartLoading">
            <canvas ref="typeChartRef" />
          </ChartPanel>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>活跃任务（最近 10 条）</span>
          <el-button text type="primary" @click="loadData">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>
      <el-table :data="activeTasks" v-loading="loading" stripe style="width: 100%">
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
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getDashboardOverview } from '@/api/admin'
import { getTasks } from '@/api/task'
import { useChartJs } from '@/composables/useChartJs'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'

const { loadChartJs } = useChartJs()

const loading = ref(false)
const chartLoading = ref(false)
const stats = ref({ total: 0, completed: 0, running: 0, error: 0 })
const activeTasks = ref([])

const trendChartRef = ref(null)
const statusChartRef = ref(null)
const typeChartRef = ref(null)

let trendChart = null
let statusChart = null
let typeChart = null

const STAT_CARDS = [
  { key: 'total', label: '全部任务', background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
  { key: 'completed', label: '已完成', background: 'linear-gradient(135deg, #10b981, #059669)' },
  { key: 'running', label: '运行中', background: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { key: 'error', label: '异常', background: 'linear-gradient(135deg, #ef4444, #dc2626)' },
]

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const [overviewRes, tasksRes] = await Promise.allSettled([
      getDashboardOverview(),
      getTasks({ page: 1, per_page: 10, status: 'running' }),
    ])

    if (overviewRes.status === 'fulfilled') {
      const data = overviewRes.value?.data || overviewRes.value || {}
      stats.value = {
        total: data.total ?? 0,
        completed: data.completed ?? 0,
        running: data.running ?? 0,
        error: data.error ?? 0,
      }
      renderCharts(data)
    }

    if (tasksRes.status === 'fulfilled') {
      const data = tasksRes.value?.data || tasksRes.value || {}
      activeTasks.value = data.tasks || data.items || data || []
    }
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

async function renderCharts(data) {
  chartLoading.value = true
  try {
    const Chart = await loadChartJs()

    // Trend line chart
    if (trendChartRef.value) {
      trendChart?.destroy()
      const trendData = data.trend || {}
      trendChart = new Chart(trendChartRef.value, {
        type: 'line',
        data: {
          labels: trendData.labels || [],
          datasets: [
            { label: '完成', data: trendData.completed || [], borderColor: '#10b981', tension: 0.3, fill: false },
            { label: '创建', data: trendData.created || [], borderColor: '#3b82f6', tension: 0.3, fill: false },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
      })
    }

    // Status pie chart
    if (statusChartRef.value) {
      statusChart?.destroy()
      statusChart = new Chart(statusChartRef.value, {
        type: 'doughnut',
        data: {
          labels: ['已完成', '运行中', '待执行', '错误', '已取消'],
          datasets: [{
            data: [
              data.status_completed ?? stats.value.completed,
              data.status_running ?? stats.value.running,
              data.status_pending ?? 0,
              data.status_error ?? stats.value.error,
              data.status_cancelled ?? 0,
            ],
            backgroundColor: ['#10b981', '#f59e0b', '#94a3b8', '#ef4444', '#6b7280'],
          }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
      })
    }

    // Type bar chart
    if (typeChartRef.value) {
      typeChart?.destroy()
      const types = data.types || {}
      typeChart = new Chart(typeChartRef.value, {
        type: 'bar',
        data: {
          labels: Object.keys(types),
          datasets: [{ label: '任务数', data: Object.values(types), backgroundColor: '#6366f1' }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
      })
    }
  } catch {
    // chart.js load failed
  } finally {
    chartLoading.value = false
  }
}

onBeforeUnmount(() => {
  trendChart?.destroy()
  statusChart?.destroy()
  typeChart?.destroy()
})

usePolling(loadData, { interval: 30000 })
onMounted(loadData)
</script>

<style lang="scss" scoped>
.admin-dashboard {
  padding: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mb-4 {
  margin-bottom: 16px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
