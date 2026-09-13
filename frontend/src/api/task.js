import api from './index'

export const getTasks = (params = {}) => api.get('/tasks', {
  params: { page: 1, per_page: 20, ...params },
})
export const getTask = (id) => api.get(`/tasks/${id}`)
export const createTask = (data) => api.post('/tasks', data)
export const batchCreateTasks = (data) => api.post('/tasks/batch-create', data)
export const deleteTask = (id) => api.delete(`/tasks/${id}`)
export const updateTaskConfig = (id, data) => api.put(`/tasks/${id}/config`, data)
export const cancelTask = (id) => api.post(`/tasks/${id}/cancel`)
export const getTaskLogs = (id) => api.get(`/tasks/${id}/logs`)
export const getTaskResults = (id, params) => api.get(`/tasks/${id}/results`, { params })
export const checkTaskStatus = (id) => api.get(`/tasks/${id}/status-check`)
export const restartTask = (id, data = {}) => api.post(`/tasks/${id}/restart`, data)
export const createRestartTask = (id) => api.post(`/tasks/${id}/create-restart`)

// 合并导出（C3 多任务打包 Excel）：流式下载，onProgress 实时汇报字节进度，返回 { blob, filename }。
// 走原生 fetch 而非 axios：需要 ReadableStream 读取进度；鉴权头与 api/index.js 拦截器同源（localStorage JWT）。
export async function exportTasksBatchStream(taskIds, { onProgress, signal } = {}) {  const token = localStorage.getItem('access_token')
  const resp = await fetch('/api/exports/tasks/batch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ task_ids: taskIds }),
    signal,
  })
  if (!resp.ok) {
    const payload = await resp.json().catch(() => ({}))
    throw new Error(payload.message || `请求失败 (${resp.status})`)
  }

  const contentLength = parseInt(resp.headers.get('Content-Length') || '0', 10)
  const disposition = resp.headers.get('Content-Disposition') || ''
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i)
  const filename = filenameMatch
    ? decodeURIComponent(filenameMatch[1].replace(/"/g, ''))
    : 'export.xlsx'

  if (!resp.body) {
    const blob = await resp.blob()
    onProgress?.({ received: blob.size, total: blob.size, percent: 100 })
    return { blob, filename }
  }

  const reader = resp.body.getReader()
  const chunks = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    onProgress?.({
      received,
      total: contentLength || 0,
      percent: contentLength ? Math.round((received / contentLength) * 100) : -1,
    })
  }

  const blob = new Blob(chunks, { type: resp.headers.get('Content-Type') || 'application/octet-stream' })
  return { blob, filename }
}

// 单任务结果导出 Excel：GET /api/exports/tasks/{task_id} 文件流下载（对齐静态版 exportResultsToCSV）。
// 走原生 fetch 以读取 Content-Disposition 文件名；返回 { blob, filename }（filename 可能为空，由调用方回退）。
export async function exportTaskResults(taskId) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(`/api/exports/tasks/${encodeURIComponent(taskId)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    const text = await resp.text()
    let message = `导出失败，状态码 ${resp.status}`
    try {
      const payload = JSON.parse(text)
      message = payload.message || message
    } catch {
      if (text) message = text
    }
    throw new Error(message)
  }

  const blob = await resp.blob()
  const disposition = resp.headers.get('Content-Disposition') || ''
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i)
  const filename = utf8Match
    ? decodeURIComponent(utf8Match[1])
    : asciiMatch
      ? asciiMatch[1]
      : ''
  return { blob, filename }
}
