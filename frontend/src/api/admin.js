import { rawApi } from './index'

export const getDashboardOverview = () => rawApi.get('/admin/api/dashboard/overview')
export const getTaskRuntimeDetail = (id) => rawApi.get(`/admin/api/tasks/${id}/runtime-detail`)
export const getModelSummary = (params) => rawApi.get('/admin/api/model-summary', { params })
export const rebuildModelSummary = () => rawApi.post('/admin/api/model-summary/rebuild')
export const getModelSummaryRebuildStatus = () => rawApi.get('/admin/api/model-summary/rebuild/status')
