import api from './index'

export const getVersions = () => api.get('/meta/versions')
export const getEnums = () => api.get('/meta/enums')
export const getNav = () => api.get('/meta/nav')

// Navigation Menu Items CRUD
export const getNavigationItems = () => api.get('/navigation-menu-items')
export const createNavigationItem = (data) => api.post('/navigation-menu-items', data)
export const updateNavigationItem = (id, data) => api.put(`/navigation-menu-items/${id}`, data)
export const deleteNavigationItem = (id) => api.delete(`/navigation-menu-items/${id}`)
