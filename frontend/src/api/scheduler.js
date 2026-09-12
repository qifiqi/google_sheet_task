import api from './index'

export const getSchedulerStats = () => api.get('/admin/scheduler/stats')
export const getScheduledTasks = (params) => api.get('/admin/scheduler/tasks', { params })
export const createScheduledTask = (data) => api.post('/admin/scheduler/tasks', data)
export const updateScheduledTask = (id, data) => api.put(`/admin/scheduler/tasks/${id}`, data)
export const deleteScheduledTask = (id) => api.delete(`/admin/scheduler/tasks/${id}`)
export const toggleScheduledTask = (id) => api.post(`/admin/scheduler/tasks/${id}/toggle`)
export const runScheduledTask = (id) => api.post(`/admin/scheduler/tasks/${id}/run`)
