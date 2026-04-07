import api from './index'

export const getTemplates = (params) => api.get('/templates', { params })
export const createTemplate = (data) => api.post('/templates', data)
export const getTemplate = (id) => api.get(`/templates/${id}`)
export const updateTemplate = (id, data) => api.put(`/templates/${id}`, data)
export const deleteTemplate = (id) => api.delete(`/templates/${id}`)
export const getResults = (params) => api.get('/results', { params })
export const getResult = (id) => api.get(`/results/${id}`)
export const deleteResult = (id) => api.delete(`/results/${id}`)
