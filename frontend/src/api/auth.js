import axios from 'axios'
import api from './index'

export const login = (data) => api.post('/auth/login', data)
export const refreshToken = (data) => api.post('/auth/refresh', data)
export const logout = () => api.post('/auth/logout')
export const getMe = () => api.get('/auth/me')

// 主服务 SSO 换票（对齐静态版 performSsoExchange）：令牌只走 header，不进
// body/URL/访问日志；响应为统一信封，token 在 data 里。用原生 axios 绕开
// api 实例的 401 刷新拦截器——本接口免登，换票失败的 401 不得触发刷新或
// 重定向，由调用方静默降级到账密登录表单。
export async function ssoExchange(token) {
  const res = await axios.post('/api/auth/sso/exchange', {}, {
    headers: { 'Content-Type': 'application/json', Token: token },
  })
  const payload = res.data
  if (!payload || payload.code !== 0) {
    throw new Error((payload && payload.message) || '主服务登录失败')
  }
  return payload.data || {}
}
export const changePassword = (data) => api.put('/auth/password', data)
export const getUsers = (params) => api.get('/admin/users', { params })
export const createUser = (data) => api.post('/admin/users', data)
export const updateUser = (id, data) => api.put(`/admin/users/${id}`, data)
export const deleteUser = (id) => api.delete(`/admin/users/${id}`)
export const getRoles = (params) => api.get('/admin/roles', { params })
export const createRole = (data) => api.post('/admin/roles', data)
export const updateRole = (id, data) => api.put(`/admin/roles/${id}`, data)
export const deleteRole = (id) => api.delete(`/admin/roles/${id}`)
export const getPermissions = () => api.get('/admin/permissions')
