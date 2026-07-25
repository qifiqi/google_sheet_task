import { computed } from 'vue'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { requestJson } from '../api/http'
import type { AnalysisRecord, AnalysisSource, WorksheetResponse } from '../types/analysis'

interface SourceFormPayload {
  googleSheetUrl: string
  spreadsheetId: string
  worksheetName: string
}

export function useAnalysisResult(source: AnalysisSource, resultId?: string) {
  const resultQuery = useQuery({
    queryKey: ['analysis-result', source, resultId],
    enabled: source !== 'xpl-v1' && Boolean(resultId),
    queryFn: async () => {
      const prefix = source === 'backtest-training' ? '/backtest-training' : '/backtest-multi-product'
      const payload = await requestJson<{ status: string; result: AnalysisRecord }>(`${prefix}/api/task-result/${encodeURIComponent(resultId || '')}`)
      return extractAnalysisResult(payload.result)
    },
  })
  const analyzeV1Mutation = useMutation({
    mutationFn: async (payload: SourceFormPayload) => {
      const response = await requestJson<{ status: string; results: AnalysisRecord }>('/xpl/v1/analyze', {
        method: 'POST',
        body: JSON.stringify({
          google_sheet_url: payload.googleSheetUrl,
          spreadsheet_id: payload.spreadsheetId,
          google_sheet_name: payload.worksheetName,
        }),
      })
      return response.results
    },
  })
  const worksheetMutation = useMutation({
    mutationFn: async (spreadsheetId: string) => {
      const payload = await requestJson<WorksheetResponse>('/api/google-sheet/worksheets', {
        method: 'POST',
        body: JSON.stringify({ spreadsheet_id: spreadsheetId }),
      })
      return payload.data || payload
    },
  })
  const result = computed(() => source === 'xpl-v1' ? analyzeV1Mutation.data.value || null : resultQuery.data.value || null)
  const loading = computed(() => resultQuery.isFetching.value || analyzeV1Mutation.isPending.value || worksheetMutation.isPending.value)
  const errorMessage = computed(() => toErrorMessage(resultQuery.error.value || analyzeV1Mutation.error.value || worksheetMutation.error.value))
  const worksheetNames = computed(() => Array.isArray(worksheetMutation.data.value?.worksheets) ? worksheetMutation.data.value.worksheets : [])
  const spreadsheetTitle = computed(() => worksheetMutation.data.value?.title || '')

  async function loadBacktestResult() {
    await resultQuery.refetch()
    if (resultQuery.error.value) throw resultQuery.error.value
    return resultQuery.data.value
  }

  async function loadWorksheets(spreadsheetId: string) {
    return worksheetMutation.mutateAsync(spreadsheetId)
  }

  async function analyzeV1(payload: SourceFormPayload) {
    return analyzeV1Mutation.mutateAsync(payload)
  }

  return {
    result,
    loading,
    errorMessage,
    worksheetNames,
    spreadsheetTitle,
    loadBacktestResult,
    loadWorksheets,
    analyzeV1,
  }
}

function extractAnalysisResult(payload: AnalysisRecord): AnalysisRecord {
  if (isRecord(payload.calculate_metrics)) {
    return {
      ...payload.calculate_metrics,
      sheet_result: isRecord(payload.sheet_result) ? payload.sheet_result : payload.sheet_result || {},
      model_name: payload.model_name || '',
    }
  }
  return payload
}

function toErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : ''
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
