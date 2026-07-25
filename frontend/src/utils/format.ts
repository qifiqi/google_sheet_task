import dayjs from 'dayjs'

export function formatDateTime(value?: string | null) {
  if (!value) {
    return '-'
  }
  const date = dayjs(value)
  if (!date.isValid()) {
    return '-'
  }
  return date.format('YYYY-MM-DD HH:mm:ss')
}

export function formatDuration(seconds?: number | null) {
  if (seconds === null || seconds === undefined) {
    return '-'
  }
  if (seconds < 60) {
    return `${Math.round(seconds)} 秒`
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`
  }
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
}

export function taskStatusText(status?: string) {
  const statusMap: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    cancelled: '已取消',
    error: '执行出错',
  }
  return statusMap[status ?? ''] ?? status ?? '-'
}

export function taskStatusType(status?: string) {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'success'
  if (status === 'pending') return 'primary'
  if (status === 'error') return 'danger'
  return 'info'
}
