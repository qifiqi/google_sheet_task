import { rawApi } from './index'

const BASE = '/backtest-multi-product/api'

export function importExcel(formData) { return rawApi.post(`${BASE}/import-excel`, formData) }
export function searchStocks(params) { return rawApi.get(`${BASE}/search-stocks`, { params }) }
export function getTaskResults(taskId, params) { return rawApi.get(`${BASE}/task-results/${taskId}`, { params }) }
export function getTaskResult(resultId) { return rawApi.get(`${BASE}/task-result/${resultId}`) }
export function getGlobalPreview(taskId) { return rawApi.get(`${BASE}/global-preview/${taskId}`) }
export function updateRatios(taskId, data) { return rawApi.put(`${BASE}/global-preview/${taskId}/ratios`, data) }
export function exportGlobalPreview(taskId) { return rawApi.get(`${BASE}/global-preview/${taskId}/export`, { responseType: 'blob' }) }
