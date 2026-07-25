import { computed } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { requestJson } from '../api/http'
import type { DashboardOverview } from '../types/api'

const dashboardQueryKey = ['dashboard-overview'] as const

const emptySummary = {
  total_tasks: 0,
  completed_tasks: 0,
  running_tasks: 0,
  error_tasks: 0,
  cancelled_tasks: 0,
  pending_tasks: 0,
}

async function fetchDashboardOverview() {
  const data = await requestJson<DashboardOverview>('/admin/api/dashboard/overview')
  if (!data.success) throw new Error('仪表盘接口返回失败')
  return data
}

export function useDashboardOverview() {
  const queryClient = useQueryClient()
  const dashboardQuery = useQuery({
    queryKey: dashboardQueryKey,
    queryFn: fetchDashboardOverview,
  })
  const overview = computed(() => dashboardQuery.data.value ?? null)
  const summary = computed(() => overview.value?.summary ?? emptySummary)
  const completionRate = computed(() => {
    const total = summary.value.total_tasks
    return total ? Math.round((summary.value.completed_tasks / total) * 100) : 0
  })
  const errorMessage = computed(() => dashboardQuery.error.value instanceof Error ? dashboardQuery.error.value.message : '')
  const loading = computed(() => dashboardQuery.isPending.value || dashboardQuery.isFetching.value)

  async function loadDashboard(showToast = false) {
    try {
      await queryClient.invalidateQueries({ queryKey: dashboardQueryKey })
      await dashboardQuery.refetch({ throwOnError: true })
      if (showToast) ElMessage.success('工作台已刷新')
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '加载工作台失败')
    }
  }

  return { overview, loading, errorMessage, summary, completionRate, loadDashboard }
}
