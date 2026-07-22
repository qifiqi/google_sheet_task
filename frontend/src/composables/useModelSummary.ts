import { readonly, shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type {
  ModelSummaryRebuildJob,
  ModelSummaryResponse,
} from '../types/api'

export interface ModelSummaryFilters {
  taskType: string
  stockKeyword: string
  marketType: string
  resultDateFrom: string
  resultDateTo: string
  periodFilter: string
  taskId: string
  resultId: string
  summaryType: 'task' | 'stock'
  bestOnly: boolean
  excessReturnMin: string
}

export function createDefaultModelSummaryFilters(): ModelSummaryFilters {
  return {
    taskType: '', stockKeyword: '', marketType: '', resultDateFrom: '', resultDateTo: '',
    periodFilter: '', taskId: '', resultId: '', summaryType: 'task', bestOnly: true, excessReturnMin: '',
  }
}

function toQueryParams(filters: ModelSummaryFilters, page: number, perPage: number) {
  const params = new URLSearchParams({
    page: String(page), per_page: String(perPage), summary_type: filters.summaryType,
    best_only: String(filters.bestOnly),
  })
  const values: Record<string, string> = {
    task_type: filters.taskType, stock_code: filters.stockKeyword.trim(), market_type: filters.marketType,
    result_date_from: filters.resultDateFrom, result_date_to: filters.resultDateTo,
    period_filter: filters.periodFilter, task_id: filters.taskId.trim(), result_id: filters.resultId,
    excess_return_min: filters.excessReturnMin,
  }
  Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value) })
  return params
}

export function useModelSummary() {
  const response = shallowRef<ModelSummaryResponse | null>(null)
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  async function load(filters: ModelSummaryFilters, page = 1, perPage = 50) {
    loading.value = true
    errorMessage.value = ''
    try {
      response.value = await requestJson<ModelSummaryResponse>(`/admin/api/model-summary?${toQueryParams(filters, page, perPage)}`)
      return response.value
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载单模型汇总失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function startRebuild(options: { taskType: string; taskId: string; batchSize: number; reset: boolean }) {
    return requestJson<{ status: string; job: ModelSummaryRebuildJob }>('/admin/api/model-summary/rebuild', {
      method: 'POST',
      body: JSON.stringify({
        task_type: options.taskType || undefined,
        task_id: options.taskId.trim() || undefined,
        batch_size: options.batchSize,
        reset: options.reset,
      }),
    })
  }

  async function getRebuildStatus(jobId: string) {
    return requestJson<{ status: string; job: ModelSummaryRebuildJob | null }>(
      `/admin/api/model-summary/rebuild/status?job_id=${encodeURIComponent(jobId)}`,
    )
  }

  return { response: readonly(response), loading: readonly(loading), errorMessage: readonly(errorMessage), load, startRebuild, getRebuildStatus, toQueryParams }
}
