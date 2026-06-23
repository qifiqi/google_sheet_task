import api from './index'

export const getConfig = () => api.get('/config')
export const updateConfig = (data) => api.post('/config', data)
export const validateConfig = () => api.get('/config/validate')
export const getSystemConfigs = () => api.get('/system-configs')
export const updateSystemConfig = (key, data) => api.put(`/system-configs/${key}`, data)
export const getLogs = (params) => api.get('/logs', { params })
export const getLatestLogs = (params) => api.get('/logs/latest', { params })
