import axios from 'axios'
import { goToMainWebLogin } from '@/config/auth'

// 鉴权模式（单 Token 子服务模式，2026-09 启用）:
// - Token 由主 Web（stock.stplan.cn）登录后颁发，前端存于
//   localStorage.access_token，随每个请求放入 `Token` 请求头;
// - 服务端（子服务）通过远程 GetUserInfo 校验 Token，不再有
//   refresh_token 换发流程; 401（Token 失效）时清空本地 Token 并
//   跳回主 Web 重新登录，本站不再展示本地登录页。
// 旧的 Bearer + refresh_token 双令牌拦截器实现注释保留在下方。

let isRefreshing = false
let pendingRequests = []

function attachInterceptors(client) {
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Token = token
      // 旧双令牌模式: config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  client.interceptors.response.use(
    (res) => res.data,
    async (err) => {
      const originalRequest = err.config
      if (err.response?.status === 401 && originalRequest && !originalRequest._retry) {
        // 单 Token 模式: 子服务无法刷新主 Web 颁发的 Token，Token 失效时
        // 清空本地登录态并跳回主 Web 重新登录（旧实现跳本地 /login）。
        originalRequest._retry = true
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        goToMainWebLogin()
        return Promise.reject(err)
      }
      return Promise.reject(err)
    }
  )

  // ---------- 旧双令牌（Bearer + refresh_token）实现，注释保留 ----------
  // client.interceptors.request.use((config) => {
  //   const token = localStorage.getItem('access_token')
  //   if (token) {
  //     config.headers.Authorization = `Bearer ${token}`
  //   }
  //   return config
  // })
  //
  // client.interceptors.response.use(
  //   (res) => res.data,
  //   async (err) => {
  //     const originalRequest = err.config
  //     if (err.response?.status === 401 && originalRequest && !originalRequest._retry) {
  //       if (isRefreshing) {
  //         return new Promise((resolve, reject) => {
  //           pendingRequests.push({ resolve, reject })
  //         }).then(() => {
  //           originalRequest.headers.Authorization = `Bearer ${localStorage.getItem('access_token')}`
  //           return client(originalRequest)
  //         })
  //       }
  //
  //       originalRequest._retry = true
  //       isRefreshing = true
  //
  //       try {
  //         const rt = localStorage.getItem('refresh_token')
  //         if (!rt) throw new Error('No refresh token')
  //         const res = await axios.post('/api/auth/refresh', { refresh_token: rt })
  //         const newToken = res.data.data.access_token
  //         localStorage.setItem('access_token', newToken)
  //         pendingRequests.forEach((p) => p.resolve())
  //         pendingRequests = []
  //         originalRequest.headers.Authorization = `Bearer ${newToken}`
  //         return client(originalRequest)
  //       } catch {
  //         localStorage.removeItem('access_token')
  //         localStorage.removeItem('refresh_token')
  //         pendingRequests.forEach((p) => p.reject(err))
  //         pendingRequests = []
  //         window.location.href = '/login'
  //         return Promise.reject(err)
  //       } finally {
  //         isRefreshing = false
  //       }
  //     }
  //     return Promise.reject(err)
  //   }
  // )

  return client
}

export function createHttpClient(config = {}) {
  return attachInterceptors(axios.create({
    timeout: 30000,
    ...config,
  }))
}

const api = createHttpClient({
  baseURL: '/api',
})

export const rawApi = createHttpClient()

export default api
