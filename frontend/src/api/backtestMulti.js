import { rawApi } from './index'

const BASE = '/backtest-multi-product/api'

export function importExcel(formData) { return rawApi.post(`${BASE}/import-excel`, formData) }
export function searchStocks(params) { return rawApi.get('/api/search-stocks', { params }) }
export function getTaskResults(taskId, params) { return rawApi.get(`${BASE}/task-results/${taskId}`, { params }) }
export function getTaskResult(resultId) { return rawApi.get(`${BASE}/task-result/${resultId}`) }
export function getGlobalPreview(taskId) { return rawApi.get(`${BASE}/global-preview/${taskId}`) }
export function calculateRatios(taskId, data) { return rawApi.post(`${BASE}/global-preview/${taskId}/calculate-ratios`, data) }
export function updateRatios(taskId, data) { return rawApi.put(`${BASE}/global-preview/${taskId}/ratios`, data) }
// 收益序列纯数据（净值为 Excel 公式，前端生成工作簿）
export function getReturnSeries(taskId, data) { return rawApi.post(`${BASE}/global-preview/${taskId}/return-series`, data) }
// XLSX 导出；query 形如 { export_name } 或 { ratios: JSON 串 }（未保存的预览比例）
export function exportGlobalPreview(taskId, params) { return rawApi.get(`/api/exports/global-previews/${taskId}`, { params, responseType: 'blob' }) }

// 通用文件流导出（fetch 而非 axios：rawApi 的 blob 拦截器拿不到响应头，
// 文件名需要读 Content-Disposition；鉴权头与 api/index.js 拦截器同源 localStorage JWT）。
async function postBlobExport(path, payload, fallbackFilename) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}))
    throw new Error(data.message || `导出失败（HTTP ${resp.status}）`)
  }
  const disposition = resp.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename[^;=\n]*=(?:UTF-8''|")?([^;\n"]+)/i)
  const filename = match ? decodeURIComponent(match[1].replace(/^"|"$/g, '')) : fallbackFilename
  const blob = await resp.blob()
  return { blob, filename }
}

// 批量导出当前页已完成任务的 ZIP（静态版 Api.endpoints.export.globalPreviewsBatch）
export function exportGlobalPreviewsBatch(taskIds) {
  return postBlobExport('/api/exports/global-previews/batch', { task_ids: taskIds }, 'backtest_multi_product_global_preview_batch.zip')
}

// Word 报告（RPT-M）下载，返回 { blob, filename }（Content-Disposition 优先，回退 fallbackFilename）
export function exportWordReportDownload(payload, fallbackFilename = 'RPT-M.docx') {
  return postBlobExport('/api/exports/backtest-reports/word', payload, fallbackFilename)
}

// 旧版封装保留：Word 报告 blob 下载（不需要服务端文件名的调用方）
export function exportWordReport(data) { return rawApi.post('/api/exports/backtest-reports/word', data, { responseType: 'blob' }) }
