import { computed, onMounted, readonly, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { requestJson } from '../api/http'
import type { DashboardOverview } from '../types/api'

const emptySummary = {
  total_tasks: 0,
  completed_tasks: 0,
  running_tasks: 0,
  error_tasks: 0,
  cancelled_tasks: 0,
  pending_tasks: 0,
}

export function useDashboardOverview() {
  const overview = shallowRef<DashboardOverview | null>(null)
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  const summary = computed(() => overview.value?.summary ?? emptySummary)
  const completionRate = computed(() => {
    const total = summary.value.total_tasks
    return total ? Math.round((summary.value.completed_tasks / total) * 100) : 0
  })

  async function loadDashboard(showToast = false) {
    loading.value = true
    errorMessage.value = ''
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
      errorMessage.value = error instanceof Error ? error.message : '加载工作台失败'
      ElMessage.error(errorMessage.value)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => loadDashboard())

  return {
    overview: readonly(overview),
    loading: readonly(loading),
    errorMessage: readonly(errorMessage),
    summary,
    completionRate,
    loadDashboard,
  }
}
