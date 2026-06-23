import api from './index'

export const getTasks = (params = {}) => api.get('/tasks', {
  params: { page: 1, per_page: 20, ...params },
})
export const getTask = (id) => api.get(`/tasks/${id}`)
export const createTask = (data) => api.post('/tasks', data)
export const batchCreateTasks = (data) => api.post('/tasks/batch-create', data)
export const deleteTask = (id) => api.delete(`/tasks/${id}`)
export const updateTaskConfig = (id, data) => api.put(`/tasks/${id}/config`, data)
export const cancelTask = (id) => api.post(`/tasks/${id}/cancel`)
export const getTaskLogs = (id) => api.get(`/tasks/${id}/logs`)
export const getTaskResults = (id, params) => api.get(`/tasks/${id}/results`, { params })
export const checkTaskStatus = (id) => api.get(`/tasks/${id}/status-check`)
export const restartTask = (id, data = {}) => api.post(`/tasks/${id}/restart`, data)
export const createRestartTask = (id) => api.post(`/tasks/${id}/create-restart`)
export const getTaskSystemLogs = (id) => api.get(`/tasks/${id}/system-logs`)
