import api from './index'

export const getDatabaseStatus = () => api.get('/database/status')
export const vacuumDatabase = () => api.post('/database/vacuum')
export const getDatabaseSuggestions = () => api.get('/database/suggestions')
