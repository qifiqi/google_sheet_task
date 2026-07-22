<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import DashboardAlerts from '../../components/dashboard/DashboardAlerts.vue'
import DashboardExecutionHealth from '../../components/dashboard/DashboardExecutionHealth.vue'
import DashboardMetricGrid from '../../components/dashboard/DashboardMetricGrid.vue'
import DashboardRecentTasks from '../../components/dashboard/DashboardRecentTasks.vue'
import DashboardResourceGrid from '../../components/dashboard/DashboardResourceGrid.vue'
import DashboardTrendCard from '../../components/dashboard/DashboardTrendCard.vue'
import { useDashboardOverview } from '../../composables/useDashboardOverview'
import type { DashboardExecutionHealth as DashboardExecutionHealthData } from '../../types/api'
import { formatDateTime } from '../../utils/format'

const emptyExecutionHealth: DashboardExecutionHealthData = {
  results: { total: 0, success: 0, failed: 0, success_rate: 0 },
  xpl_jobs: {
    total: 0,
    pending: 0,
    running: 0,
    retrying: 0,
    completed: 0,
    error: 0,
    cancelled: 0,
    backlog: 0,
    avg_compute_seconds: null,
  },
}

const {
  overview,
  loading,
  errorMessage,
  summary,
  completionRate,
  loadDashboard,
} = useDashboardOverview()
const router = useRouter()

const executionHealth = computed(() => overview.value?.execution_health ?? emptyExecutionHealth)

function openTaskList() {
  router.push({ name: 'Tasks' })
}
</script>

<template>
  <section v-loading="loading" class="dashboard-view">
    <header class="dashboard-header">
      <div>
        <span>系统运行概览</span>
        <h1>工作台</h1>
      </div>
      <p>{{ overview?.checked_at ? `数据更新于 ${formatDateTime(overview.checked_at)}` : '正在读取运行数据' }}</p>
    </header>

    <el-alert
      v-if="errorMessage"
      :closable="false"
      show-icon
      type="warning"
      :title="errorMessage"
    />

    <DashboardMetricGrid :summary="summary" :execution-health="executionHealth" />

    <div class="dashboard-main-grid">
      <DashboardTrendCard
        :items="overview?.daily_trend ?? []"
        @refresh="loadDashboard(true)"
      />
      <DashboardExecutionHealth
        :health="executionHealth"
        :summary="summary"
        :completion-rate="completionRate"
      />
    </div>

    <DashboardResourceGrid :resources="overview?.resource_health ?? {}" />

    <div class="dashboard-bottom-grid">
      <DashboardRecentTasks
        :tasks="overview?.recent_tasks ?? []"
        :checked-at="overview?.checked_at"
        @view="openTaskList"
      />
      <DashboardAlerts
        :alerts="overview?.recent_alerts ?? []"
        @view="openTaskList"
      />
    </div>
  </section>
</template>

<style scoped>
.dashboard-view {
  display: grid;
  gap: 18px;
}

.dashboard-header {
  min-height: 52px;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
}

.dashboard-header > div {
  display: grid;
  gap: 2px;
}

.dashboard-header span,
.dashboard-header p {
  margin: 0;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.dashboard-header h1 {
  margin: 0;
  color: var(--admin-text);
  font-size: 20px;
  font-weight: 600;
}

.dashboard-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
}

.dashboard-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1180px) {
  .dashboard-main-grid,
  .dashboard-bottom-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    align-items: start;
    flex-direction: column;
    gap: 4px;
  }
}
</style>
