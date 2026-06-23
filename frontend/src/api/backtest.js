import { rawApi } from './index'

export const importExcel = (data) => rawApi.post('/backtest-training/api/import-excel', data)
export const searchStocks = (params) => rawApi.get('/backtest-training/api/search-stocks', { params })
export const getTaskResults = (taskId, params) => rawApi.get(`/backtest-training/api/task-results/${taskId}`, { params })
export const getTaskResult = (id) => rawApi.get(`/backtest-training/api/task-result/${id}`)
export const getTaskSummary = (taskId) => rawApi.get(`/backtest-training/api/task-summary/${taskId}`)
export const getGlobalPreview = (taskId) => rawApi.get(`/backtest-training/api/global-preview/${taskId}`)
export const exportGlobalPreview = (taskId) => rawApi.get(`/backtest-training/api/global-preview/${taskId}/export`, { responseType: 'blob' })
