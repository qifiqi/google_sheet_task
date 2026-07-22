import { readonly, shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { AnalysisRecord, AnalysisSource, WorksheetResponse } from '../types/analysis'

interface SourceFormPayload {
  googleSheetUrl: string
  spreadsheetId: string
  worksheetName: string
}

export function useAnalysisResult(source: AnalysisSource) {
  const result = shallowRef<AnalysisRecord | null>(null)
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')
  const worksheetNames = shallowRef<string[]>([])
  const spreadsheetTitle = shallowRef('')

  async function loadBacktestResult(resultId: string) {
    const prefix = source === 'backtest-training' ? '/backtest-training' : '/backtest-multi-product'
    return load(() => requestJson<{ status: string; result: AnalysisRecord }>(`${prefix}/api/task-result/${encodeURIComponent(resultId)}`))
  }

  async function loadWorksheets(spreadsheetId: string) {
    const payload = await requestJson<WorksheetResponse>('/api/google-sheet/worksheets', {
      method: 'POST',
      body: JSON.stringify({ spreadsheet_id: spreadsheetId }),
    })
    const response = payload.data || payload
    worksheetNames.value = Array.isArray(response.worksheets) ? response.worksheets : []
    spreadsheetTitle.value = response.title || ''
  }

  async function analyzeV1(payload: SourceFormPayload) {
    return load(() => requestJson<{ status: string; results: AnalysisRecord }>('/xpl/v1/analyze', {
      method: 'POST',
      body: JSON.stringify({
        google_sheet_url: payload.googleSheetUrl,
        spreadsheet_id: payload.spreadsheetId,
        google_sheet_name: payload.worksheetName,
      }),
    }), 'results')
  }

  async function load<T extends { result?: AnalysisRecord; results?: AnalysisRecord }>(request: () => Promise<T>, resultKey: 'result' | 'results' = 'result') {
    loading.value = true
    errorMessage.value = ''
    try {
      const payload = await request()
      const nextResult = payload[resultKey]
      if (!nextResult || typeof nextResult !== 'object') throw new Error('接口未返回分析结果')
      result.value = normalizeResult(nextResult)
      return result.value
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载分析结果失败'
      result.value = null
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    result: readonly(result),
    loading: readonly(loading),
    errorMessage: readonly(errorMessage),
    worksheetNames: readonly(worksheetNames),
    spreadsheetTitle: readonly(spreadsheetTitle),
    loadBacktestResult,
    loadWorksheets,
    analyzeV1,
  }
}

function normalizeResult(payload: AnalysisRecord): AnalysisRecord {
  if (isRecord(payload.calculate_metrics)) {
    return {
      ...payload.calculate_metrics,
      sheet_result: isRecord(payload.sheet_result) ? payload.sheet_result : payload.sheet_result || {},
      model_name: payload.model_name || '',
    }
  }
  return payload
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
