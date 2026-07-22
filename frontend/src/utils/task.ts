import type { TaskItem } from '../types/api'

const taskTypeLabels: Record<string, string> = {
  google_sheet: 'Google Sheet C3',
  google_sheet_c4: 'Google Sheet C4',
  google_sheet_c5: 'Google Sheet C5',
  google_sheet_c7: 'Google Sheet C7',
  google_sheet_c31: 'Google Sheet C31',
  backtest_training: '单品数据回测',
  backtest_multi_product: '多品数据回测',
}

const xplStatusLabels: Record<string, string> = {
  pending: '待处理',
  running: '运行中',
  retrying: '重试中',
  completed: '已完成',
  error: '失败',
  cancelled: '已取消',
}

export function taskTypeText(value?: string | null) {
  const key = String(value || '').toLowerCase()
  return taskTypeLabels[key] || value || '-'
}

export function templateTaskTypeText(value?: string | null) {
  return taskTypeText(value || 'google_sheet')
}

export function templateOverview(config: Record<string, unknown>) {
  const sheets = Array.isArray(config.sheets) ? config.sheets.length : config.spreadsheet_id ? 1 : 0
  const stockCodes = Array.isArray(config.stock_codes)
    ? config.stock_codes.map(String)
    : config.stock_code ? [String(config.stock_code)] : []
  const parameters = Array.isArray(config.parameters) ? config.parameters : []
  const dimensions = Array.isArray(config.parameter_dimensions)
    ? config.parameter_dimensions.length
    : parameters.filter(Array.isArray).length
  const values = parameters.reduce((count, item) => count + (Array.isArray(item) ? item.length : 0), 0)

  return {
    sheetLabel: sheets ? `${sheets} 个 Sheet` : '未配置 Sheet',
    stockLabel: stockCodes.length ? stockCodes.slice(0, 2).join('、') : '未指定标的',
    stockOverflow: Math.max(stockCodes.length - 2, 0),
    parameterLabel: dimensions ? `${dimensions} 个维度 / ${values} 个值` : '未配置参数',
  }
}

export function taskProgress(task: TaskItem) {
  const total = Number(task.total_steps || 0)
  const current = Number(task.current_step || 0)
  return total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
}

export function xplStatusText(value?: string | null) {
  return xplStatusLabels[String(value || '').toLowerCase()] || value || '-'
}

export function xplStatusType(value?: string | null) {
  const status = String(value || '').toLowerCase()
  if (status === 'completed') return 'success'
  if (status === 'running') return 'success'
  if (status === 'retrying') return 'warning'
  if (status === 'error') return 'danger'
  return status === 'pending' ? 'primary' : 'info'
}

export function shortIdentifier(value?: string | number | null) {
  const text = String(value || '')
  return text.length > 16 ? `${text.slice(0, 8)}...${text.slice(-4)}` : text || '-'
}

function normalizeTaskType(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

export function isGoogleSheetTask(value?: string | null) {
  return ['google_sheet', 'google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7'].includes(normalizeTaskType(value))
}

export function taskExecutionUrl(task: Pick<TaskItem, 'id' | 'task_type'>) {
  const taskType = normalizeTaskType(task.task_type)
  if (taskType === 'backtest_training') return `/backtest-training/detail/${encodeURIComponent(task.id)}`
  if (taskType === 'backtest_multi_product') return `/backtest-multi-product/detail/${encodeURIComponent(task.id)}`

  const params = new URLSearchParams({ task_id: task.id })
  const version = taskType.replace('google_sheet_', '')
  if (version && version !== 'google_sheet') params.set('version', version)
  return `/google-sheet/detail?${params}`
}

export function taskRestartCreateUrl(task: Pick<TaskItem, 'id' | 'task_type'>) {
  const taskType = normalizeTaskType(task.task_type)
  if (taskType === 'backtest_training') return '/backtest-training/create'
  if (taskType === 'backtest_multi_product') return '/backtest-multi-product/create'

  const params = new URLSearchParams({ restart_task_id: task.id })
  const version = taskType.replace('google_sheet_', '')
  if (version && version !== 'google_sheet') params.set('version', version)
  return `/google-sheet/create?${params}`
}
