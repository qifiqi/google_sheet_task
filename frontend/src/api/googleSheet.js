import api from './index'

export const getWorksheets = (data) => api.post('/google-sheet/worksheets', data)
export const getGoogleSheets = (params) => api.get('/google-sheets', { params })
export const createGoogleSheet = (data) => api.post('/google-sheets', data)
export const getGoogleSheet = (id) => api.get(`/google-sheets/${id}`)
export const updateGoogleSheet = (id, data) => api.put(`/google-sheets/${id}`, data)
export const deleteGoogleSheet = (id) => api.delete(`/google-sheets/${id}`)
export const getTokens = (params) => api.get('/google-sheet-tokens', { params })
export const getToken = (id) => api.get(`/google-sheet-tokens/${id}`)
export const updateToken = (id, data) => api.put(`/google-sheet-tokens/${id}`, data)
export const deleteToken = (id) => api.delete(`/google-sheet-tokens/${id}`)
export const importToken = (data) => api.post('/google-sheet-tokens/import', data)
