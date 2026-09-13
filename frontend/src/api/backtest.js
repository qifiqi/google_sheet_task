import { rawApi } from './index'

export const importExcel = (data) => rawApi.post('/backtest-training/api/import-excel', data)
export const searchStocks = (params) => rawApi.get('/api/search-stocks', { params })
export const getTaskResults = (taskId, params) => rawApi.get(`/backtest-training/api/task-results/${taskId}`, { params })
export const getTaskResult = (id) => rawApi.get(`/backtest-training/api/task-result/${id}`)
export const getTaskResultExportPreview = (id) => rawApi.get(`/backtest-training/api/task-result/${id}/export-preview`)
export const getTaskSummary = (taskId) => rawApi.get(`/backtest-training/api/task-summary/${taskId}`)
export const getGlobalPreview = (taskId) => rawApi.get(`/backtest-training/api/global-preview/${taskId}`)
export const exportBacktestResultCsv = (resultId) =>
  rawApi.get(`/api/exports/backtest-results/${encodeURIComponent(resultId)}`, { responseType: 'blob' })

// 回测专用文件流下载（原生 fetch）：axios blob 拦截器拿不到响应头，
// 而 Content-Disposition 里的文件名（filename*/filename）需要从响应头解析，
// 鉴权头与 api/index.js 拦截器同源（localStorage JWT）。
async function fetchDownload(url, { method = 'GET', body } = {}) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(url, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    let message = `请求失败 (${resp.status})`
    try {
      const payload = await resp.json()
      message = payload.message || message
    } catch {
      // 非 JSON 错误体，保留默认 message
    }
    throw new Error(message)
  }
  const blob = await resp.blob()
  return { blob, disposition: resp.headers.get('Content-Disposition') || '' }
}

// 解析 Content-Disposition 文件名：优先 filename*=UTF-8''，回退 filename，最后用 fallback。
export function resolveDownloadFilename(contentDisposition, fallback) {
  const encodedMatch = String(contentDisposition || '').match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch) {
    try {
      return decodeURIComponent(encodedMatch[1])
    } catch {
      return encodedMatch[1]
    }
  }
  const plainMatch = String(contentDisposition || '').match(/filename="?([^";]+)"?/i)
  return plainMatch ? plainMatch[1] : fallback
}

// 全局预览 XLSX 导出（单品回测），返回 { blob, filename }。
export async function exportGlobalPreview(taskId) {
  const { blob, disposition } = await fetchDownload(`/api/exports/global-previews/${encodeURIComponent(taskId)}`)
  return { blob, filename: resolveDownloadFilename(disposition, `global_preview_${taskId}.xlsx`) }
}

// 全局预览批量 ZIP 导出（单品回测列表页），body { task_ids }，返回 { blob, filename }。
export async function exportGlobalPreviewsBatch(taskIds) {
  const { blob, disposition } = await fetchDownload('/api/exports/global-previews/batch', {
    method: 'POST',
    body: { task_ids: taskIds },
  })
  return { blob, filename: resolveDownloadFilename(disposition, 'backtest_training_global_preview_batch.zip') }
}

// 回测 Word 报告导出（RPT-S），payload 为 task-result 响应中的 word_report_payload，返回 { blob, filename }。
export async function exportBacktestWordReport(payload) {
  const { blob, disposition } = await fetchDownload('/api/exports/backtest-reports/word', {
    method: 'POST',
    body: payload,
  })
  return { blob, filename: resolveDownloadFilename(disposition, 'RPT-S.docx') }
}
