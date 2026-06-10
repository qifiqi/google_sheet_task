import { rawApi } from './index'
import api from './index'

export const getDashboardOverview = () => rawApi.get('/admin/api/dashboard/overview')
export const getTaskRuntimeDetail = (id) => rawApi.get(`/admin/api/tasks/${id}/runtime-detail`)
export const getAsyncTaskStatus = () => rawApi.get('/admin/api/scheduler/status')
export const cleanupAsyncTasks = () => rawApi.post('/admin/api/scheduler/cleanup')

// Model Summary
export const modelSummary = (params) => api.get('/admin/model-summary', { params })
export const exportModelSummary = (params) => api.get('/admin/model-summary/export', { params, responseType: 'blob' })
export const rebuildModelSummary = () => api.post('/admin/model-summary/rebuild')
export const getRebuildStatus = () => api.get('/admin/model-summary/rebuild/status')
