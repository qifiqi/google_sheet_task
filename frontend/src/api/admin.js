import { rawApi } from './index'

export const getDashboardOverview = () => rawApi.get('/admin/api/dashboard/overview')
export const getTaskRuntimeDetail = (id) => rawApi.get(`/admin/api/tasks/${id}/runtime-detail`)
