import { rawApi } from './index'

// 独立全局预览中心（/global-preview 自有 API）
export const getPreviewTask = (taskId) => rawApi.get(`/global-preview/api/tasks/${taskId}`)
export const previewGroup = (taskId, data) => rawApi.post(`/global-preview/api/tasks/${taskId}/preview-group`, data)
