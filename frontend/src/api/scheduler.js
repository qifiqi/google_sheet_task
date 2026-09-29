import api from './index'

export const getSchedulerStats = () => api.get('/admin/scheduler/stats')
export const getScheduledTasks = (params) => api.get('/admin/scheduler/tasks', { params })
export const createScheduledTask = (data) => api.post('/admin/scheduler/tasks', data)
export const updateScheduledTask = (id, data) => api.put(`/admin/scheduler/tasks/${id}`, data)
export const deleteScheduledTask = (id) => api.delete(`/admin/scheduler/tasks/${id}`)
// toggle 显式提交目标状态 {is_active}（对齐静态版 toggleTask 语义）
export const toggleScheduledTask = (id, data) => api.post(`/admin/scheduler/tasks/${id}/toggle`, data)
export const runScheduledTask = (id) => api.post(`/admin/scheduler/tasks/${id}/run`)
