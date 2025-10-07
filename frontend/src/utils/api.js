import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 在请求发送前做一些处理
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    // 统一错误处理
    let message = '请求失败'
    
    if (error.response) {
      // 服务器返回错误状态码
      const { status, data } = error.response
      
      switch (status) {
        case 400:
          message = data.message || '请求参数错误'
          break
        case 401:
          message = '未授权访问'
          break
        case 403:
          message = '禁止访问'
          break
        case 404:
          message = '请求的资源不存在'
          break
        case 500:
          message = data.message || '服务器内部错误'
          break
        default:
          message = data.message || `请求失败 (${status})`
      }
    } else if (error.request) {
      // 网络错误
      message = '网络连接失败，请检查网络设置'
    } else {
      // 其他错误
      message = error.message || '未知错误'
    }
    
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default api
