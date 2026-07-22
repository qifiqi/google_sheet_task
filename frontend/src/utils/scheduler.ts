import type { ScheduledTask } from '../types/api'

const taskTypeLabels: Record<string, string> = {
  cleanup: '数据清理',
  backup: '数据备份',
  maintenance: '系统维护',
  custom: '自定义',
}

const functionLabels: Record<string, string> = {
  cleanup_old_logs: '清理旧日志',
  cleanup_old_results: '清理旧结果',
  cleanup_old_data: '清理旧数据',
}

export const scheduledTaskTypeOptions = Object.entries(taskTypeLabels).map(([value, label]) => ({ value, label }))
export const scheduledFunctionOptions = Object.entries(functionLabels).map(([value, label]) => ({ value, label }))

export function scheduledTaskTypeText(value?: string | null) {
  return taskTypeLabels[String(value || '')] || value || '-'
}

export function scheduledFunctionText(value?: string | null) {
  return functionLabels[String(value || '')] || value || '-'
}

export function scheduledTaskStatus(task: ScheduledTask) {
  return task.is_active ? '启用' : '停用'
}

export function scheduledTaskStatusType(task: ScheduledTask) {
  return task.is_active ? 'success' : 'info'
}
