<script setup lang="ts">
import { computed, onMounted, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Calendar,
  CircleCheck,
  DataLine,
  Loading,
  MoreFilled,
  Refresh,
  Tickets,
  WarningFilled,
} from '@element-plus/icons-vue'
import { requestJson } from '../api/http'
import type { DashboardOverview } from '../types/api'

interface SummaryCard {
  label: string
  value: number
  note: string
  tone: 'blue' | 'cyan' | 'green' | 'red'
}

interface RuntimeTask {
  id?: string
  name?: string
  task_type?: string
  status?: string
  created_at?: string
  progress_percentage?: number
}

const overview = shallowRef<DashboardOverview | null>(null)
const loading = shallowRef(false)
const loadError = shallowRef('')

const summary = computed(() => overview.value?.summary || {})
const trendItems = computed(() => overview.value?.daily_trend || [])
const recentTasks = computed(() => (overview.value?.recent_tasks || []) as RuntimeTask[])
const activeTasks = computed(() => (overview.value?.active_tasks || []) as RuntimeTask[])

const summaryCards = computed<SummaryCard[]>(() => [
  {
    label: '任务总数',
    value: Number(summary.value.total_tasks || 0),
    note: '当前可见任务',
    tone: 'blue',
  },
  {
    label: '已完成',
    value: Number(summary.value.completed_tasks || 0),
    note: '执行成功任务',
    tone: 'green',
  },
  {
    label: '运行中',
    value: Number(summary.value.running_tasks || 0),
    note: '后台线程活跃',
    tone: 'cyan',
  },
  {
    label: '异常任务',
    value: Number(summary.value.error_tasks || 0),
    note: '需要排查',
    tone: 'red',
  },
])

const barValues = computed(() => {
  const values = trendItems.value.map((item) => Number(item.created || 0) + Number(item.completed || 0))
  const max = Math.max(...values, 1)
  return values.map((value) => Math.max(18, Math.round((value / max) * 74)))
})

const completionRate = computed(() => {
  const total = Number(summary.value.total_tasks || 0)
  if (!total) {
    return 0
  }
  return Math.round((Number(summary.value.completed_tasks || 0) / total) * 100)
})

function statusText(status?: string) {
  const statusMap: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    cancelled: '已取消',
    error: '执行出错',
  }
  return statusMap[status || ''] || status || '-'
}

function statusType(status?: string) {
  if (status === 'completed') {
    return 'success'
  }
  if (status === 'running') {
    return 'warning'
  }
  if (status === 'error') {
    return 'danger'
  }
  return 'info'
}

function formatTime(value?: string) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN')
}

async function loadDashboard(showToast = false) {
  loading.value = true
  loadError.value = ''
  try {
    const data = await requestJson<DashboardOverview>('/admin/api/dashboard/overview')
    if (!data.success) {
      throw new Error('仪表盘接口返回失败')
    }
    overview.value = data
    if (showToast) {
      ElMessage.success('工作台已刷新')
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '加载工作台失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadDashboard(false)
})
</script>

<template>
  <section v-loading="loading" class="dashboard-view">
    <div class="dashboard-hero">
      <div class="dashboard-hero__copy">
        <h1>欢迎回来，任务平台管理员</h1>
        <p>基于当前账号权限展示任务运行态、执行趋势与最近活动。</p>
        <div class="dashboard-hero__identity">
          <span class="dashboard-hero__logo">J</span>
          <div>
            <strong>Jaspil 任务平台</strong>
            <span>Google Sheet 参数校验与回测运维工作台</span>
          </div>
        </div>
      </div>
      <div class="dashboard-hero__art" aria-hidden="true">
        <div class="dashboard-hero__panel">
          <span></span><span></span><span></span>
        </div>
        <div class="dashboard-hero__chart">
          <i></i><i></i><i></i><i></i>
        </div>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      :closable="false"
      class="dashboard-error"
      show-icon
      type="warning"
      :title="loadError"
    />

    <div class="dashboard-grid dashboard-grid--summary">
      <el-card v-for="card in summaryCards" :key="card.label" shadow="never" class="metric-card">
        <div class="metric-card__head">
          <span>{{ card.label }}</span>
          <el-tag size="small" effect="light" :type="card.tone === 'red' ? 'danger' : 'primary'">
            实时
          </el-tag>
        </div>
        <div class="metric-card__body">
          <strong>{{ card.value.toLocaleString('zh-CN') }}</strong>
          <span>{{ card.note }}</span>
        </div>
        <div class="metric-card__bars" :class="`is-${card.tone}`">
          <i v-for="height in [42, 58, 34, 66, 48, 54]" :key="`${card.label}-${height}`" :style="{ height: `${height}px` }"></i>
        </div>
      </el-card>
    </div>

    <div class="dashboard-grid dashboard-grid--main">
      <el-card shadow="never" class="trend-card">
        <template #header>
          <div class="dashboard-card-header">
            <div>
              <strong>任务趋势</strong>
              <span>近 7 天创建 / 完成</span>
            </div>
            <el-button :icon="Refresh" size="small" text type="primary" @click="loadDashboard(true)" />
          </div>
        </template>
        <div class="trend-card__line">
          <svg viewBox="0 0 720 180" role="img" aria-label="任务趋势折线图">
            <defs>
              <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#6687ff" stop-opacity="0.25" />
                <stop offset="100%" stop-color="#6687ff" stop-opacity="0" />
              </linearGradient>
            </defs>
            <path d="M0 112 C90 104 118 100 190 108 C274 120 304 134 392 113 C475 94 520 102 598 83 C654 69 690 58 720 50" fill="none" stroke="#6687ff" stroke-width="4" />
            <path d="M0 112 C90 104 118 100 190 108 C274 120 304 134 392 113 C475 94 520 102 598 83 C654 69 690 58 720 50 L720 180 L0 180 Z" fill="url(#trendFill)" />
          </svg>
        </div>
        <div class="trend-card__bars">
          <span v-for="(height, index) in barValues" :key="index" :style="{ height: `${height}px` }"></span>
        </div>
      </el-card>

      <el-card shadow="never" class="progress-card">
        <template #header>
          <div class="dashboard-card-header">
            <div>
              <strong>完成率</strong>
              <span>已完成 / 总任务</span>
            </div>
            <el-icon><CircleCheck /></el-icon>
          </div>
        </template>
        <el-progress type="dashboard" :percentage="completionRate" :stroke-width="12" color="#6687ff" />
        <div class="progress-card__legend">
          <span><i></i> 已完成 {{ summary.completed_tasks || 0 }}</span>
          <span><i></i> 总任务 {{ summary.total_tasks || 0 }}</span>
        </div>
      </el-card>
    </div>

    <div class="dashboard-grid dashboard-grid--bottom">
      <el-card shadow="never" class="activity-card">
        <template #header>
          <div class="dashboard-card-header">
            <div>
              <strong>最近任务</strong>
              <span>{{ overview?.checked_at ? `更新于 ${formatTime(overview.checked_at)}` : '等待数据' }}</span>
            </div>
            <el-icon><Tickets /></el-icon>
          </div>
        </template>
        <el-table :data="recentTasks" row-key="id" class="dashboard-table" empty-text="暂无最近任务">
          <el-table-column prop="name" label="任务" min-width="190" show-overflow-tooltip />
          <el-table-column prop="task_type" label="类型" width="150" show-overflow-tooltip />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="150">
            <template #default="{ row }">
              <el-progress :percentage="Number(row.progress_percentage || 0)" :show-text="false" />
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="side-card">
        <template #header>
          <div class="dashboard-card-header">
            <div>
              <strong>最近活动</strong>
              <span>运行中任务列表</span>
            </div>
            <el-icon><MoreFilled /></el-icon>
          </div>
        </template>
        <div v-if="activeTasks.length" class="activity-list">
          <div v-for="task in activeTasks" :key="task.id || task.name" class="activity-list__item">
            <span class="activity-list__icon"><el-icon><Loading /></el-icon></span>
            <div>
              <strong>{{ task.name || task.id }}</strong>
              <span>{{ task.task_type || '任务' }} · {{ Number(task.progress_percentage || 0) }}%</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="当前没有运行中的任务" :image-size="86" />
      </el-card>
    </div>

    <div class="dashboard-grid dashboard-grid--footer">
      <el-card shadow="never" class="mini-card">
        <el-icon><DataLine /></el-icon>
        <div>
          <strong>{{ summary.pending_tasks || 0 }}</strong>
          <span>待执行任务</span>
        </div>
      </el-card>
      <el-card shadow="never" class="mini-card">
        <el-icon><WarningFilled /></el-icon>
        <div>
          <strong>{{ summary.cancelled_tasks || 0 }}</strong>
          <span>已取消任务</span>
        </div>
      </el-card>
      <el-card shadow="never" class="mini-card">
        <el-icon><Calendar /></el-icon>
        <div>
          <strong>{{ trendItems.length }}</strong>
          <span>趋势采样天数</span>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.dashboard-view {
  display: grid;
  gap: 20px;
}

.dashboard-hero {
  min-height: 216px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 20px;
  overflow: hidden;
  padding: 28px 32px;
  border: 1px solid #dce5f8;
  border-radius: 8px;
  background: linear-gradient(135deg, #eaf0ff 0%, #f6f9ff 100%);
}

.dashboard-hero__copy h1 {
  margin: 0;
  color: #242947;
  font-size: 27px;
  font-weight: 800;
  letter-spacing: 0;
}

.dashboard-hero__copy p {
  margin: 12px 0 36px;
  color: #7e8aa6;
  font-size: 14px;
}

.dashboard-hero__identity {
  display: flex;
  align-items: center;
  gap: 16px;
}

.dashboard-hero__logo {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(135deg, #5d7cff, #42d3c6);
  color: #fff;
  font-size: 28px;
  font-weight: 900;
}

.dashboard-hero__identity div {
  display: grid;
  gap: 6px;
}

.dashboard-hero__identity strong {
  color: #242947;
  font-size: 18px;
}

.dashboard-hero__identity span {
  color: #7280a1;
  font-size: 14px;
}

.dashboard-hero__art {
  position: relative;
  min-height: 160px;
}

.dashboard-hero__panel,
.dashboard-hero__chart {
  position: absolute;
  border: 1px solid rgba(102, 135, 255, 0.24);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 18px 50px rgba(87, 110, 180, 0.12);
}

.dashboard-hero__panel {
  right: 74px;
  top: 22px;
  width: 134px;
  height: 82px;
  padding: 14px;
}

.dashboard-hero__panel span {
  display: block;
  height: 8px;
  margin-bottom: 10px;
  border-radius: 99px;
  background: #8fb0ff;
}

.dashboard-hero__panel span:nth-child(2) {
  width: 72%;
}

.dashboard-hero__panel span:nth-child(3) {
  width: 52%;
}

.dashboard-hero__chart {
  right: 18px;
  bottom: 18px;
  width: 176px;
  height: 100px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 14px;
  padding: 18px;
}

.dashboard-hero__chart i {
  width: 18px;
  border-radius: 8px 8px 3px 3px;
  background: linear-gradient(180deg, #6687ff, #42d3c6);
}

.dashboard-hero__chart i:nth-child(1) { height: 36px; }
.dashboard-hero__chart i:nth-child(2) { height: 58px; }
.dashboard-hero__chart i:nth-child(3) { height: 44px; }
.dashboard-hero__chart i:nth-child(4) { height: 70px; }

.dashboard-grid {
  display: grid;
  gap: 20px;
}

.dashboard-grid--summary {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.dashboard-grid--main {
  grid-template-columns: minmax(0, 1fr) 300px;
}

.dashboard-grid--bottom {
  grid-template-columns: minmax(0, 1fr) 390px;
}

.dashboard-grid--footer {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-card,
.trend-card,
.progress-card,
.activity-card,
.side-card,
.mini-card {
  border-radius: 8px;
  border-color: #e4e8f0;
}

.metric-card :deep(.el-card__body) {
  min-height: 172px;
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 14px;
}

.metric-card__head,
.dashboard-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metric-card__head span,
.dashboard-card-header span {
  color: #7886a3;
  font-size: 13px;
}

.dashboard-card-header > div {
  display: grid;
  gap: 6px;
}

.dashboard-card-header strong {
  color: #242947;
  font-size: 18px;
  font-weight: 700;
}

.metric-card__body {
  display: grid;
  gap: 6px;
}

.metric-card__body strong {
  color: #1f2544;
  font-size: 28px;
  font-weight: 500;
}

.metric-card__body span {
  color: #7786a3;
  font-size: 13px;
}

.metric-card__bars {
  align-self: end;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 16px;
}

.metric-card__bars i {
  width: 18px;
  border-radius: 6px;
  background: linear-gradient(180deg, #8ba5ff, #6282f8);
}

.metric-card__bars.is-cyan i {
  background: linear-gradient(180deg, #8ba5ff, #42c7e7);
}

.metric-card__bars.is-green i {
  background: linear-gradient(180deg, #79e0bd, #18b984);
}

.metric-card__bars.is-red i {
  background: linear-gradient(180deg, #ffb0b0, #ff6b6b);
}

.trend-card__line {
  height: 186px;
}

.trend-card__line svg {
  width: 100%;
  height: 100%;
}

.trend-card__bars {
  height: 82px;
  display: flex;
  align-items: end;
  justify-content: space-around;
  padding: 0 16px 8px;
}

.trend-card__bars span {
  width: 28px;
  border-radius: 8px 8px 4px 4px;
  background: linear-gradient(180deg, #8ba5ff, #6282f8);
}

.progress-card :deep(.el-card__body) {
  display: grid;
  place-items: center;
  gap: 18px;
}

.progress-card__legend {
  display: flex;
  gap: 14px;
  color: #7886a3;
  font-size: 12px;
}

.progress-card__legend i {
  width: 8px;
  height: 8px;
  display: inline-block;
  margin-right: 5px;
  border-radius: 50%;
  background: #6687ff;
}

.dashboard-table {
  width: 100%;
}

.side-card :deep(.el-card__body) {
  min-height: 300px;
}

.activity-list {
  display: grid;
  gap: 14px;
}

.activity-list__item {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.activity-list__icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #eef4ff;
  color: #6687ff;
}

.activity-list__item div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.activity-list__item strong {
  overflow: hidden;
  color: #242947;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-list__item span {
  color: #7886a3;
  font-size: 12px;
}

.mini-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
}

.mini-card .el-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #eef4ff;
  color: #6687ff;
  font-size: 22px;
}

.mini-card div {
  display: grid;
  gap: 4px;
}

.mini-card strong {
  color: #242947;
  font-size: 24px;
}

.mini-card span {
  color: #7886a3;
  font-size: 13px;
}

.dashboard-error {
  border-radius: 8px;
}

@media (max-width: 1280px) {
  .dashboard-grid--summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-grid--main,
  .dashboard-grid--bottom {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .dashboard-hero,
  .dashboard-grid--summary,
  .dashboard-grid--footer {
    grid-template-columns: 1fr;
  }

  .dashboard-hero {
    padding: 22px;
  }

  .dashboard-hero__art {
    display: none;
  }
}
</style>
