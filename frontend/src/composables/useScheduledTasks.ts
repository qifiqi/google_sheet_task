import { reactive, shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type {
  SchedulerStats,
  SchedulerStatsResponse,
  SchedulerTaskListResponse,
  SchedulerTaskPayload,
  ScheduledTask,
} from '../types/api'

interface SchedulerFilters {
  keyword: string
  taskType: string
  active: '' | 'true' | 'false'
}

const EMPTY_STATS: SchedulerStats = {
  total_tasks: 0,
  active_tasks: 0,
  inactive_tasks: 0,
  scheduler_running: false,
}

export function useScheduledTasks() {
  const tasks = shallowRef<ScheduledTask[]>([])
  const stats = shallowRef<SchedulerStats>({ ...EMPTY_STATS })
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')
  const filters = reactive<SchedulerFilters>({ keyword: '', taskType: '', active: '' })
  const pagination = reactive({ page: 1, per_page: 20, total: 0, pages: 0 })

  async function load(page = pagination.page) {
    loading.value = true
    errorMessage.value = ''
    const params = new URLSearchParams({ page: String(page), per_page: String(pagination.per_page) })
    if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
    if (filters.taskType) params.set('task_type', filters.taskType)
    if (filters.active) params.set('is_active', filters.active)

    try {
      const [taskData, statsData] = await Promise.all([
        requestJson<SchedulerTaskListResponse>(`/api/admin/scheduler/tasks?${params}`),
        requestJson<SchedulerStatsResponse>('/api/admin/scheduler/stats'),
      ])
      if (!taskData.success) throw new Error(taskData.message || '加载定时任务失败')
      if (!statsData.success) throw new Error(statsData.message || '加载调度状态失败')
      tasks.value = taskData.tasks
      stats.value = statsData.stats
      Object.assign(pagination, taskData.pagination)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载定时任务失败'
    } finally {
      loading.value = false
    }
  }

  async function create(payload: SchedulerTaskPayload) {
    await requestJson('/api/admin/scheduler/tasks', { method: 'POST', body: JSON.stringify(payload) })
    await load(1)
  }

  async function update(taskId: number, payload: SchedulerTaskPayload) {
    await requestJson(`/api/admin/scheduler/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify(payload) })
    await load()
  }

  async function toggle(task: ScheduledTask) {
    await requestJson(`/api/admin/scheduler/tasks/${task.id}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ is_active: !task.is_active }),
    })
    await load()
  }

  async function run(task: ScheduledTask) {
    await requestJson(`/api/admin/scheduler/tasks/${task.id}/run`, { method: 'POST' })
    await load()
  }

  async function remove(task: ScheduledTask) {
    await requestJson(`/api/admin/scheduler/tasks/${task.id}`, { method: 'DELETE' })
    const nextPage = tasks.value.length === 1 && pagination.page > 1 ? pagination.page - 1 : pagination.page
    await load(nextPage)
  }

  function resetFilters() {
    filters.keyword = ''
    filters.taskType = ''
    filters.active = ''
  }

  return { tasks, stats, loading, errorMessage, filters, pagination, load, create, update, toggle, run, remove, resetFilters }
}
