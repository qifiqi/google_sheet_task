import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { requestJson } from '../api/http'
import type { DashboardOverview } from '../types/api'

const dashboardQueryKey = ['dashboard-overview'] as const
const dashboardPeriodOptions = [7, 30, 90] as const

export type DashboardPeriodDays = typeof dashboardPeriodOptions[number]

const emptySummary = {
  total_tasks: 0,
  completed_tasks: 0,
  running_tasks: 0,
  error_tasks: 0,
  cancelled_tasks: 0,
  pending_tasks: 0,
}

async function fetchDashboardOverview(days: DashboardPeriodDays) {
  const data = await requestJson<DashboardOverview>(`/admin/api/dashboard/overview?days=${days}`)
  if (!data.success) throw new Error('仪表盘接口返回失败')
  return data
}

export function useDashboardOverview() {
  const queryClient = useQueryClient()
  const selectedDays = ref<DashboardPeriodDays>(30)
  const dashboardQuery = useQuery({
    queryKey: computed(() => [...dashboardQueryKey, selectedDays.value]),
    queryFn: () => fetchDashboardOverview(selectedDays.value),
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
      await queryClient.invalidateQueries({ queryKey: [...dashboardQueryKey, selectedDays.value] })
      await dashboardQuery.refetch({ throwOnError: true })
      if (showToast) ElMessage.success('工作台已刷新')
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '加载工作台失败')
    }
  }

  function setSelectedDays(days: DashboardPeriodDays) {
    selectedDays.value = days
  }

  return {
    overview,
    loading,
    errorMessage,
    summary,
    completionRate,
    selectedDays,
    setSelectedDays,
    loadDashboard,
  }
}
