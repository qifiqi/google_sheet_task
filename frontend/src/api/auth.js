import api from './index'

// 单 Token 子服务模式（2026-09 起）:
// - 本服务不提供账号密码登录 / 注册 / 刷新令牌，仅保留登录校验（getMe）
//   与登出（logout）；Token 由主 Web 登录后颁发，随请求头 `Token` 传递。
// - 用户 / 角色 / 权限管理接口已随本地 RBAC 一并注释停用
//   （后端路由见 app/routes/auth_api.py 注释块），恢复时取消注释即可。

export const logout = () => api.post('/auth/logout')
export const getMe = () => api.get('/auth/me')

// ---------- 本地登录 / 账号体系接口（已停用，注释保留） ----------
// export const login = (data) => api.post('/auth/login', data)
// export const refreshToken = (data) => api.post('/auth/refresh', data)
// export const changePassword = (data) => api.put('/auth/password', data)
// export const getUsers = (params) => api.get('/admin/users', { params })
// export const createUser = (data) => api.post('/admin/users', data)
// export const updateUser = (id, data) => api.put(`/admin/users/${id}`, data)
// export const deleteUser = (id) => api.delete(`/admin/users/${id}`)
// export const getRoles = (params) => api.get('/admin/roles', { params })
// export const createRole = (data) => api.post('/admin/roles', data)
// export const updateRole = (id, data) => api.put(`/admin/roles/${id}`, data)
// export const deleteRole = (id) => api.delete(`/admin/roles/${id}`)
// export const getPermissions = () => api.get('/admin/permissions')
