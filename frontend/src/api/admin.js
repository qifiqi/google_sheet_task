import api, { rawApi } from './index'

export const getDashboardOverview = () => rawApi.get('/admin/api/dashboard/overview')
export const getTaskRuntimeDetail = (id) => rawApi.get(`/admin/api/tasks/${id}/runtime-detail`)
// 任务停止确认（/api/tasks/*：api/task.js 不允许改动，暂挂 admin.js）
export const getTaskStopConfirmation = (id) => api.get(`/tasks/${id}/stop-confirmation`)
export const getModelSummary = (params) => rawApi.get('/admin/api/model-summary', { params })
export const rebuildModelSummary = () => rawApi.post('/admin/api/model-summary/rebuild')
export const getModelSummaryRebuildStatus = (params) => rawApi.get('/admin/api/model-summary/rebuild/status', { params })
