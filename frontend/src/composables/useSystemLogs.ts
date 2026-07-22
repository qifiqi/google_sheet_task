import { reactive, shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { SystemLogEntry } from '../types/system'

export function useSystemLogs() {
  const logs = shallowRef<SystemLogEntry[]>([])
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')
  const filters = reactive({ level: '', search: '', date: '', taskId: '', limit: 100 })

  async function load() {
    loading.value = true
    errorMessage.value = ''
    const params = new URLSearchParams({ limit: String(filters.limit) })
    if (filters.level) params.set('level', filters.level)
    if (filters.search.trim()) params.set('search', filters.search.trim())
    if (filters.date) params.set('date', filters.date)
    if (filters.taskId.trim()) params.set('task_id', filters.taskId.trim())
    try {
      const payload = await requestJson<{ status: string; logs: SystemLogEntry[] }>(`/api/logs?${params}`)
      if (payload.status !== 'success') throw new Error('加载系统日志失败')
      logs.value = payload.logs || []
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载系统日志失败'
    } finally {
      loading.value = false
    }
  }

  function resetFilters() {
    filters.level = ''
    filters.search = ''
    filters.date = ''
    filters.taskId = ''
    filters.limit = 100
  }

  return { logs, loading, errorMessage, filters, load, resetFilters }
}
