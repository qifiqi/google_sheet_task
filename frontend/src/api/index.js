import axios from 'axios'

let isRefreshing = false
let pendingRequests = []

function attachInterceptors(client) {
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  client.interceptors.response.use(
    (res) => res.data,
    async (err) => {
      const originalRequest = err.config
      if (err.response?.status === 401 && originalRequest && !originalRequest._retry) {
        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            pendingRequests.push({ resolve, reject })
          }).then(() => {
            originalRequest.headers.Authorization = `Bearer ${localStorage.getItem('access_token')}`
            return client(originalRequest)
          })
        }

        originalRequest._retry = true
        isRefreshing = true

        try {
          const rt = localStorage.getItem('refresh_token')
          if (!rt) throw new Error('No refresh token')
          const res = await axios.post('/api/auth/refresh', { refresh_token: rt })
          const newToken = res.data.data.access_token
          localStorage.setItem('access_token', newToken)
          pendingRequests.forEach((p) => p.resolve())
          pendingRequests = []
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return client(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          pendingRequests.forEach((p) => p.reject(err))
          pendingRequests = []
          window.location.href = '/login'
          return Promise.reject(err)
        } finally {
          isRefreshing = false
        }
      }
      return Promise.reject(err)
    }
  )

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
