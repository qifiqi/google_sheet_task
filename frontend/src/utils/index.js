import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

// 设置dayjs为中文
dayjs.locale('zh-cn')

// 格式化时间
export const formatTime = (time, format = 'YYYY-MM-DD HH:mm:ss') => {
  if (!time) return '-'
  return dayjs(time).format(format)
}

// 获取相对时间
export const getRelativeTime = (time) => {
  if (!time) return '-'
  return dayjs(time).fromNow()
}

// 任务状态映射
export const taskStatusMap = {
  pending: { text: '待执行', type: 'info' },
  running: { text: '执行中', type: 'warning' },
  completed: { text: '已完成', type: 'success' },
  cancelled: { text: '已取消', type: 'info' },
  error: { text: '执行出错', type: 'danger' }
}

// 获取任务状态信息
export const getTaskStatus = (status) => {
  return taskStatusMap[status] || { text: status, type: 'info' }
}

// 日志级别映射
export const logLevelMap = {
  debug: { text: 'DEBUG', type: 'info' },
  info: { text: 'INFO', type: 'success' },
  warning: { text: 'WARNING', type: 'warning' },
  error: { text: 'ERROR', type: 'danger' }
}

// 获取日志级别信息
export const getLogLevel = (level) => {
  return logLevelMap[level] || { text: level.toUpperCase(), type: 'info' }
}

// 文件大小格式化
export const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 深拷贝
export const deepClone = (obj) => {
  if (obj === null || typeof obj !== 'object') return obj
  if (obj instanceof Date) return new Date(obj)
  if (obj instanceof Array) return obj.map(item => deepClone(item))
  if (typeof obj === 'object') {
    const clonedObj = {}
    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        clonedObj[key] = deepClone(obj[key])
      }
    }
    return clonedObj
  }
}

// 防抖函数
export const debounce = (func, wait) => {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// 节流函数
export const throttle = (func, limit) => {
  let inThrottle
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}

// 生成随机ID
export const generateId = () => {
  return Math.random().toString(36).substr(2, 9)
}

// 验证JSON格式
export const isValidJSON = (str) => {
  try {
    JSON.parse(str)
    return true
  } catch (e) {
    return false
  }
}

// 下载文件
export const downloadFile = (data, filename, type = 'application/json') => {
  const blob = new Blob([data], { type })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
