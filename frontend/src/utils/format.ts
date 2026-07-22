export function formatDateTime(value?: string | null) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '-'
  }
  const parts = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`
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
