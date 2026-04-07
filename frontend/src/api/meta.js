import api from './index'

export const getVersions = () => api.get('/meta/versions')
export const getEnums = () => api.get('/meta/enums')
export const getNav = () => api.get('/meta/nav')
