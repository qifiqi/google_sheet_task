import { computed, reactive, shallowRef } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { requestJson } from '../api/http'
import { downloadFile } from '../utils/download'
import type { TaskItem, TaskListResponse } from '../types/api'

export const C3_MERGE_EXPORT_LIMIT = 10

export function useC3MergeExport() {
  const filters = reactive({ keyword: '', status: '' })
  const queryState = reactive({ keyword: '', status: '', page: 1, perPage: 20 })
  const selectedTaskMap = shallowRef(new Map<string, TaskItem>())

  const tasksQuery = useQuery({
    queryKey: computed(() => [
      'c3-merge-export-tasks',
      queryState.keyword,
      queryState.status,
      queryState.page,
      queryState.perPage,
    ]),
    queryFn: async () => {
      const params = new URLSearchParams({
        task_type: 'google_sheet',
        page: String(queryState.page),
        per_page: String(queryState.perPage),
      })
      if (queryState.keyword) params.set('keyword', queryState.keyword)
      if (queryState.status) params.set('status', queryState.status)
      return requestJson<TaskListResponse>(`/api/tasks?${params}`)
    },
  })

  const exportMutation = useMutation({
    mutationFn: (taskIds: string[]) => downloadFile(
      '/api/tasks/batch-export',
      'C3_合并导出.csv',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_ids: taskIds }),
      },
    ),
  })

  const items = computed(() => tasksQuery.data.value?.tasks ?? [])
  const pagination = computed(() => tasksQuery.data.value?.pagination ?? {
    page: queryState.page,
    per_page: queryState.perPage,
    total: 0,
    pages: 0,
  })
  const selectedTasks = computed(() => Array.from(selectedTaskMap.value.values()))
  const selectedIds = computed(() => new Set(selectedTaskMap.value.keys()))
  const selectedCount = computed(() => selectedTaskMap.value.size)
  const loading = computed(() => tasksQuery.isPending.value || tasksQuery.isFetching.value)
  const exporting = computed(() => exportMutation.isPending.value)
  const errorMessage = computed(() => {
    const error = tasksQuery.error.value
    return error instanceof Error ? error.message : ''
  })
  const allCurrentPageSelected = computed(() => (
    items.value.length > 0 && items.value.every((task) => selectedTaskMap.value.has(task.id))
  ))
  const hasSelectedOnCurrentPage = computed(() => (
    items.value.some((task) => selectedTaskMap.value.has(task.id))
  ))

  function updateSelection(update: (next: Map<string, TaskItem>) => void) {
    const next = new Map(selectedTaskMap.value)
    update(next)
    selectedTaskMap.value = next
  }

  function toggleTask(task: TaskItem, checked: boolean) {
    if (checked && !selectedTaskMap.value.has(task.id) && selectedCount.value >= C3_MERGE_EXPORT_LIMIT) {
      ElMessage.warning(`最多选择 ${C3_MERGE_EXPORT_LIMIT} 个任务`)
      return
    }
    updateSelection((next) => checked ? next.set(task.id, task) : next.delete(task.id))
  }

  function selectCurrentPage() {
    let omitted = 0
    updateSelection((next) => {
      for (const task of items.value) {
        if (next.has(task.id)) continue
        if (next.size >= C3_MERGE_EXPORT_LIMIT) {
          omitted += 1
          continue
        }
        next.set(task.id, task)
      }
    })
    if (omitted) ElMessage.warning(`已达到 ${C3_MERGE_EXPORT_LIMIT} 个任务上限`)
  }

  function deselectCurrentPage() {
    updateSelection((next) => items.value.forEach((task) => next.delete(task.id)))
  }

  function invertCurrentPage() {
    const selectedOnPage = new Set(items.value.filter((task) => selectedTaskMap.value.has(task.id)).map((task) => task.id))
    let omitted = 0
    updateSelection((next) => {
      selectedOnPage.forEach((taskId) => next.delete(taskId))
      for (const task of items.value) {
        if (selectedOnPage.has(task.id)) continue
        if (next.size >= C3_MERGE_EXPORT_LIMIT) {
          omitted += 1
          continue
        }
        next.set(task.id, task)
      }
    })
    if (omitted) ElMessage.warning(`已达到 ${C3_MERGE_EXPORT_LIMIT} 个任务上限`)
  }

  function clearSelection() {
    selectedTaskMap.value = new Map()
  }

  function applyFilters() {
    queryState.keyword = filters.keyword.trim()
    queryState.status = filters.status
    queryState.page = 1
  }

  function resetFilters() {
    filters.keyword = ''
    filters.status = ''
    applyFilters()
  }

  function setPage(page: number) {
    queryState.page = page
  }

  function setPageSize(pageSize: number) {
    queryState.perPage = pageSize
    queryState.page = 1
  }

  async function refreshTasks() {
    await tasksQuery.refetch()
  }

  async function exportSelected() {
    const taskIds = Array.from(selectedTaskMap.value.keys())
    if (!taskIds.length) {
      ElMessage.warning('请至少选择一个任务')
      return
    }
    try {
      await exportMutation.mutateAsync(taskIds)
      ElMessage.success(`已导出 ${taskIds.length} 个 C3 任务`)
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '合并导出失败')
    }
  }

  return {
    filters,
    items,
    pagination,
    selectedTasks,
    selectedIds,
    selectedCount,
    loading,
    exporting,
    errorMessage,
    allCurrentPageSelected,
    hasSelectedOnCurrentPage,
    toggleTask,
    selectCurrentPage,
    deselectCurrentPage,
    invertCurrentPage,
    clearSelection,
    applyFilters,
    resetFilters,
    setPage,
    setPageSize,
    refreshTasks,
    exportSelected,
  }
}
