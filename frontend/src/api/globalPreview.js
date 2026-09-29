import { rawApi } from './index'
import { resolveDownloadFilename } from './backtest'

// 独立全局预览中心（/global-preview 自有 API）
export const getPreviewTask = (taskId) => rawApi.get(`/global-preview/api/tasks/${taskId}`)
export const previewGroup = (taskId, data) => rawApi.post(`/global-preview/api/tasks/${taskId}/preview-group`, data)

// 文件流下载（原生 fetch）：axios blob 拦截器拿不到响应头，而导出文件名需要
// 从 Content-Disposition 解析；鉴权头与 api/index.js 拦截器同源（localStorage JWT）。
async function fetchDownload(url) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    let message = `请求失败 (${resp.status})`
    try {
      const payload = await resp.json()
      message = payload.message || message
    } catch {
      // 非 JSON 错误体，保留默认 message
    }
    throw new Error(message)
  }
  const blob = await resp.blob()
  return { blob, disposition: resp.headers.get('Content-Disposition') || '' }
}

// 全局预览导出（对齐静态版 api.js export.globalPreviewStocks）：按股票拆 Excel
// 再合并 ZIP。此入口的历史契约始终是 ZIP，不从首屏预览元数据推断股票数量
//（首屏只预加载一个分组，无法代表整任务）。query 形如 '?export_name=...'。
export async function exportGlobalPreviewStocks(taskId, query = '') {
  const { blob, disposition } = await fetchDownload(`/api/exports/global-previews/${taskId}/stocks${query}`)
  return { blob, filename: resolveDownloadFilename(disposition, '导出文件') }
}
