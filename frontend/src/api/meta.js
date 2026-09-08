import api from './index'

export const getVersions = () => api.get('/meta/versions')
export const getEnums = () => api.get('/meta/enums')

// 路由表仅保留拉取接口：菜单来自远程 GetUserRoleList（/api/meta/nav），
// 本地路由表 CRUD 已随本地导航管理一并注释停用（后端见
// app/routes/config_api.py 注释块），恢复时取消注释。
export const getNav = () => api.get('/meta/nav')

// // Navigation Menu Items CRUD（本地路由表管理，已停用）
// export const getNavigationItems = () => api.get('/navigation-menu-items')
// export const createNavigationItem = (data) => api.post('/navigation-menu-items', data)
// export const updateNavigationItem = (id, data) => api.put(`/navigation-menu-items/${id}`, data)
// export const deleteNavigationItem = (id) => api.delete(`/navigation-menu-items/${id}`)
