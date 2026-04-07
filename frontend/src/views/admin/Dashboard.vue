<template>
  <div class="dashboard-page">

    <div class="metric-grid dashboard-metrics">
      <div
        v-for="card in summaryCards"
        :key="card.key"
        class="dashboard-metrics__item metric-card"
        :style="{ background: card.background }"
      >
        <div class="metric-card__label">{{ card.label }}</div>
        <div class="metric-card__value">{{ summary[card.key] ?? 0 }}</div>
        <div class="metric-card__hint">{{ card.hint }}</div>
      </div>
    </div>

    <el-row :gutter="16" class="dashboard-section">
      <el-col :xs="24" :md="16" style="margin-bottom: 12px">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-row">
              <span>最近 7 天任务趋势</span>
              <span class="inline-muted">{{ checkedAt }}</span>
            </div>
          </template>
          <div class="chart-shell chart-shell--trend">
            <canvas ref="trendChartRef" height="120"></canvas>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="8" style="margin-bottom: 12px">
        <el-card shadow="never">
          <template #header>状态分布</template>
          <div class="chart-shell chart-shell--small">
            <canvas ref="statusChartRef" height="220"></canvas>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="dashboard-section">
      <el-col :xs="24" :md="10" style="margin-bottom: 12px">
        <el-card shadow="never">
          <template #header>任务类型分布</template>
          <div class="chart-shell chart-shell--small">
            <canvas ref="typeChartRef" height="200"></canvas>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="14" style="margin-bottom: 12px">
        <el-card shadow="never">
          <template #header>正在运行任务</template>
          <div v-if="!activeTasks.length" class="empty-block">当前没有运行中的任务</div>
          <el-row v-else :gutter="12">
            <el-col
              v-for="task in activeTasks"
              :key="task.id"
              :xs="24"
              :sm="12"
              style="margin-bottom: 12px"
            >
              <div class="active-task-card">
                <div class="active-task-card__header">
                  <div>
                    <div class="active-task-card__name">{{ task.name }}</div>
                    <div class="inline-muted">{{ task.task_type }}</div>
                  </div>
                  <StatusTag :status="task.status" />
                </div>
                <div class="inline-muted active-task-card__meta">
                  参数组 {{ task.config_summary?.parameter_groups ?? 0 }}
                </div>
                <el-progress
                  :percentage="task.progress_percentage || 0"
                  :format="() => `${task.current_step || 0}/${task.total_steps || 0}`"
                />
                <el-button
                  link
                  type="primary"
                  size="small"
                  class="active-task-card__action"
                  @click="$router.push(`/task/${task.id}`)"
                >
                  查看详情
                </el-button>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>最近任务详情</template>
      <el-table :data="recentTasks" stripe>
        <el-table-column label="任务" min-width="180">
          <template #default="{ row }">
            <div class="recent-task-name">{{ row.name }}</div>
            <div class="inline-muted">{{ row.task_type }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="参数组" width="84">
          <template #default="{ row }">
            {{ row.config_summary?.parameter_groups ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="150">
          <template #default="{ row }">
            <el-progress
              v-if="row.total_steps > 0"
              :percentage="row.progress_percentage || 0"
              :format="() => `${row.current_step || 0}/${row.total_steps || 0}`"
            />
            <span v-else class="inline-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">
            {{ row.duration_seconds != null ? `${row.duration_seconds}s` : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getDashboardOverview } from '@/api/admin'
import StatusTag from '@/components/StatusTag.vue'
import { useResponsive } from '@/composables/useResponsive'

const { componentSize } = useResponsive()

const loading = ref(false)
const summary = ref({})
const activeTasks = ref([])
const recentTasks = ref([])
const checkedAt = ref('-')
const trendChartRef = ref()
const statusChartRef = ref()
const typeChartRef = ref()
let charts = {}
let refreshTimer = null

const summaryCards = [
  { key: 'total_tasks', label: '总任务数', hint: '全部历史任务规模', background: 'linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%)' },
  { key: 'completed_tasks', label: '已完成', hint: '成功结束的任务批次', background: 'linear-gradient(135deg, #15803d 0%, #22c55e 100%)' },
  { key: 'running_tasks', label: '运行中', hint: '当前仍在执行中的任务', background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)' },
  { key: 'error_tasks', label: '错误', hint: '需要优先关注与排查', background: 'linear-gradient(135deg, #b91c1c 0%, #ef4444 100%)' },
  { key: 'cancelled_tasks', label: '已取消', hint: '人工或流程终止的任务', background: 'linear-gradient(135deg, #475569 0%, #64748b 100%)' },
  { key: 'pending_tasks', label: '待执行', hint: '等待调度与开始运行', background: 'linear-gradient(135deg, #334155 0%, #475569 100%)' },
]

async function loadDashboard(showMessage = false) {
  loading.value = true
  try {
    const data = await getDashboardOverview()
    summary.value = data.summary || {}
    activeTasks.value = data.active_tasks || []
    recentTasks.value = data.recent_tasks || []
    checkedAt.value = data.checked_at || '-'
    await nextTick()
    renderCharts(data)
    if (showMessage) {
      ElMessage.success('仪表盘已刷新')
    }
  } catch {
    ElMessage.error('加载仪表盘失败')
  } finally {
    loading.value = false
  }
}

function upsertChart(key, canvas, config) {
  if (charts[key]) {
    charts[key].destroy()
  }
  if (!canvas || typeof Chart === 'undefined') {
    return
  }
  charts[key] = new Chart(canvas.getContext('2d'), config)
}

function renderCharts(data) {
  if (typeof Chart === 'undefined') {
    return
  }

  const trend = data.daily_trend || []
  upsertChart('trend', trendChartRef.value, {
    type: 'line',
    data: {
      labels: trend.map((item) => item.date),
      datasets: [
        {
          label: '创建',
          data: trend.map((item) => item.created),
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37, 99, 235, 0.12)',
          fill: true,
          tension: 0.3,
        },
        {
          label: '完成',
          data: trend.map((item) => item.completed),
          borderColor: '#16a34a',
          backgroundColor: 'rgba(22, 163, 74, 0.12)',
          fill: true,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top' } },
    },
  })

  const statusDistribution = data.status_distribution || {}
  upsertChart('status', statusChartRef.value, {
    type: 'doughnut',
    data: {
      labels: Object.keys(statusDistribution),
      datasets: [
        {
          data: Object.values(statusDistribution),
          backgroundColor: ['#2563eb', '#16a34a', '#f59e0b', '#ef4444', '#64748b', '#14b8a6'],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
    },
  })

  const taskTypeDistribution = data.task_type_distribution || {}
  upsertChart('type', typeChartRef.value, {
    type: 'bar',
    data: {
      labels: Object.keys(taskTypeDistribution),
      datasets: [
        {
          label: '任务数',
          data: Object.values(taskTypeDistribution),
          backgroundColor: '#1d4ed8',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
    },
  })
}

onMounted(() => {
  if (typeof Chart === 'undefined') {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'
    script.onload = () => loadDashboard()
    document.head.appendChild(script)
  } else {
    loadDashboard()
  }

  refreshTimer = setInterval(loadDashboard, 30000)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
  Object.values(charts).forEach((chart) => chart.destroy())
})
</script>

<style scoped>
.dashboard-page :deep(.el-card__body) {
  height: 100%;
}

.dashboard-hero {
  margin-bottom: 18px;
}

.dashboard-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
}

.dashboard-hero__meta-item {
  min-width: 150px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.dashboard-hero__meta-label {
  display: block;
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
}

.dashboard-hero__meta-value {
  display: block;
  margin-top: 6px;
  color: #fff;
  font-family: 'Fira Code', monospace;
  font-size: 14px;
}

.dashboard-metrics {
  margin-bottom: 18px;
}

.dashboard-metrics__item {
  grid-column: span 2;
}

.dashboard-section {
  margin-bottom: 2px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.chart-shell {
  position: relative;
  width: 100%;
}

.chart-shell--trend {
  min-height: 260px;
}

.chart-shell--small {
  min-height: 220px;
}

.empty-block {
  color: var(--app-text-muted);
  text-align: center;
  padding: 20px 0;
}

.active-task-card {
  border: 1px solid var(--app-border);
  border-radius: 18px;
  padding: 14px;
  height: 100%;
  box-sizing: border-box;
  background: linear-gradient(180deg, #fff 0%, #f7faff 100%);
}

.active-task-card__header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 12px;
}

.active-task-card__name {
  font-weight: 700;
  color: var(--app-text);
}

.active-task-card__meta {
  margin-bottom: 6px;
}

.active-task-card__action {
  margin-top: 8px;
}

.recent-task-name {
  font-weight: 700;
}

@media (max-width: 768px) {
  .dashboard-metrics__item {
    grid-column: span 6;
  }

  .chart-shell--trend {
    min-height: 220px;
  }

  .chart-shell--small {
    min-height: 200px;
  }
}

@media (max-width: 640px) {
  .dashboard-metrics__item {
    grid-column: span 12;
  }
}
</style>
