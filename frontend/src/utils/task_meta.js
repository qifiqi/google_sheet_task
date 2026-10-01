// 任务类型元信息共享工具：类型归一/可读标签/详情页路由分流。
// 消费方：admin/Tasks.vue、admin/Results.vue 等需要展示任务类型或跳任务详情的页面。

// 任务类型归一（对齐 admin/Tasks.vue 历史实现，别名归并到规范类型）
export function normalizeTaskType(taskType) {
  const normalized = String(taskType || '').trim().toLowerCase()
  if (['google_sheet', 'google_sheet_c3', 'google_sheet_c31'].includes(normalized)) return 'google_sheet'
  if (normalized === 'google_sheet_c4') return 'google_sheet_c4'
  if (normalized === 'google_sheet_c5') return 'google_sheet_c5'
  if (normalized === 'google_sheet_c7') return 'google_sheet_c7'
  if (['backtest_training', 'backtest'].includes(normalized)) return 'backtest_training'
  if (['backtest_multi_product', 'multi_product_backtest', 'backtest_multi'].includes(normalized)) return 'backtest_multi_product'
  return normalized
}

// Google Sheet 系任务 → 创建页版本标识（restart_task_id 回填跳转用）
export function getTaskVersionFromType(taskType) {
  const normalized = normalizeTaskType(taskType)
  if (normalized === 'google_sheet_c4') return 'c4'
  if (normalized === 'google_sheet_c5') return 'c5'
  if (normalized === 'google_sheet_c7') return 'c7'
  if (normalized === 'google_sheet') return 'c3'
  return ''
}

export function isGoogleSheetTask(taskType) {
  return ['google_sheet', 'google_sheet_c4', 'google_sheet_c5', 'google_sheet_c7'].includes(normalizeTaskType(taskType))
}

// 任务详情页路由分流（回测域独立详情页，其余统一 /task/:id）
export function taskDetailRoute(task) {
  const normalized = normalizeTaskType(task?.task_type)
  if (normalized === 'backtest_training') return `/backtest/${task.id}`
  if (normalized === 'backtest_multi_product') return `/backtest-multi/${task.id}`
  return `/task/${task.id}`
}

// 类型可读短标签（表格列/徽标场景）
const TASK_TYPE_LABELS = {
  google_sheet: 'C3',
  google_sheet_C4: 'C4',
  google_sheet_C5: 'C5',
  google_sheet_C7: 'C7',
  backtest_training: '单品回测',
  backtest_multi_product: '多品回测',
}

export function taskTypeLabel(value) {
  return TASK_TYPE_LABELS[value] || value || '-'
}
