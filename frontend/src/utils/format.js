// 全站统一的时间显示格式：YYYY-MM-DD HH:mm:ss
export function formatDateTime(value) {
  if (!value) return '-'
  const normalized = String(value).replace('T', ' ')
  return normalized.length > 19 ? normalized.slice(0, 19) : normalized
}
