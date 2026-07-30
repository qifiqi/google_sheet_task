export interface ApiEnvelope<T> {
  code: number
  data: T
  message: string
}

export interface UserRole {
  id?: number
  name?: string
  code?: string
}

export interface CurrentUser {
  id: number
  username: string
  is_active: boolean
  roles?: readonly UserRole[]
  permissions?: readonly string[]
  created_at?: string | null
  last_login?: string | null
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  user: CurrentUser
}

export interface RefreshResponse {
  access_token: string
  user: CurrentUser
}

export interface NavItem {
  id?: number
  key: string
  label: string
  path?: string
  permission?: string
  parent_key?: string | null
  sort_order?: number
  is_visible?: boolean
  children?: readonly NavItem[]
}

export interface DashboardSummary {
  total_tasks: number
  completed_tasks: number
  running_tasks: number
  error_tasks: number
  cancelled_tasks: number
  pending_tasks: number
}

export interface DashboardTrendPoint {
  date: string
  created: number
  completed: number
}

export interface DashboardPeriodTaskTrendPoint {
  date: string
  created: number
  completed: number
  error: number
}

export interface DashboardTaskTypeStatusPoint {
  task_type: string
  status: string
  count: number
}

export interface DashboardResultTrendPoint {
  date: string
  success: number
  failed: number
}

export interface DashboardPeriodOverview {
  days: number
  start_at: string
  task_trend: DashboardPeriodTaskTrendPoint[]
  task_type_status_distribution: DashboardTaskTypeStatusPoint[]
  result_trend: DashboardResultTrendPoint[]
}

export interface DashboardTask {
  id: string
  name: string
  task_type: string
  status: string
  current_step: number
  total_steps: number
  progress_percentage: number
  duration_seconds?: number | null
  error_message?: string | null
  start_time?: string | null
  end_time?: string | null
  created_at?: string | null
}

export interface DashboardResultHealth {
  total: number
  success: number
  failed: number
  success_rate: number
}

export interface DashboardXplHealth {
  total: number
  pending: number
  running: number
  retrying: number
  completed: number
  error: number
  cancelled: number
  backlog: number
  avg_compute_seconds?: number | null
}

export interface DashboardExecutionHealth {
  results: DashboardResultHealth
  xpl_jobs: DashboardXplHealth
}

export interface DashboardResourceHealth {
  google_sheets?: {
    total: number
    active: number
    in_use: number
    available: number
  }
  google_sheet_tokens?: {
    total: number
    active: number
    available: number
    current_usage: number
  }
  scheduled_tasks?: {
    total: number
    active: number
    running: number
    next_run_at?: string | null
  }
  backtest_locks?: {
    active: number
  }
  catalog?: {
    task_templates?: number
    stock_metadata?: number
    result_summaries?: number
    best_summaries?: number
  }
}

export interface DashboardAlert {
  id: number
  task_id: string
  task_name: string
  level: 'warning' | 'error' | string
  message: string
  timestamp?: string | null
}

export interface DashboardOverview {
  success: boolean
  summary: DashboardSummary
  status_distribution: Record<string, number>
  task_type_distribution: Record<string, number>
  daily_trend: DashboardTrendPoint[]
  period: DashboardPeriodOverview
  recent_tasks: DashboardTask[]
  active_tasks: DashboardTask[]
  execution_health: DashboardExecutionHealth
  resource_health: DashboardResourceHealth
  recent_alerts: DashboardAlert[]
  checked_at?: string
}

export interface PaginationState {
  page: number
  per_page: number
  total: number
  pages: number
  has_prev?: boolean
  has_next?: boolean
}

export interface TaskItem {
  id: string
  name: string
  description?: string | null
  status: string
  task_type: string
  config?: Record<string, unknown>
  current_step?: number
  total_steps?: number
  error_message?: string | null
  created_at?: string | null
  start_time?: string | null
  end_time?: string | null
  updated_at?: string | null
}

export interface TaskLogItem {
  id?: number
  level?: string | null
  message: string
  timestamp?: string | null
  source?: string | null
}

export interface TaskStatistics {
  total_tasks: number
  completed_tasks: number
  running_tasks: number
  error_tasks: number
  pending_tasks: number
  today_new_tasks: number
  success_rate: number
  error_rate: number
  avg_duration_minutes: number
}

export interface TaskListResponse {
  status: string
  tasks: TaskItem[]
  pagination: PaginationState
  statistics: TaskStatistics
}

export interface TaskTemplate {
  id: number
  name: string
  description?: string | null
  config: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
}

export interface TaskResultItem {
  id: number
  task_id: string
  task_name?: string
  task_type?: string
  step_index?: number | null
  success: boolean
  timestamp?: string | null
  summary?: TaskResultSummary
}

export interface TaskResultSummary {
  stock_code?: string | null
  stock_name?: string | null
  period?: string | null
  kline_date_range?: string | null
  parameter_values: string[]
  parameter_items: Array<{ label: string; value: string }>
  model_count: number
  model_names: string[]
  analysis_status?: string | null
  models?: TaskResultModelSummary[]
  metrics?: TaskResultMetricMap
}

export interface TaskResultMetricMap {
    return?: string | number | null
    annualized?: string | number | null
    max_drawdown?: string | number | null
    index_return?: string | number | null
    index_annualized?: string | number | null
    index_max_drawdown?: string | number | null
    index_sharpe?: string | number | null
    model_sharpe?: string | number | null
    fee_total?: string | number | null
    fee_annualized?: string | number | null
    turnover_rate?: string | number | null
    return_beats?: string | number | null
    dd_beats?: string | number | null
    max_one_year_beats?: string | number | null
    min_one_year_beats?: string | number | null
    max_theoretical_leverage?: string | number | null
    avg_theoretical_leverage?: string | number | null
    unit_theoretical_leverage_return?: string | number | null
    max_actual_leverage?: string | number | null
    avg_actual_leverage?: string | number | null
    unit_actual_leverage_return?: string | number | null
}

export interface TaskResultModelSummary {
  key: string
  code: string
  name: string
  analysis_status?: string | null
  metrics: TaskResultMetricMap
}

export interface TaskResultPresentationItem {
  label: string
  value: string
}

export interface TaskResultPresentationSection {
  key: 'core' | 'execution' | 'analysis' | string
  title: string
  items: TaskResultPresentationItem[]
}

export interface TaskResultPresentationModel {
  key: string
  name: string
  sections: TaskResultPresentationSection[]
}

export interface TaskResultPresentation {
  kind: 'c3' | 'c4_c5' | 'c7' | 'generic' | string
  models: TaskResultPresentationModel[]
}

export interface TaskResultListResponse {
  results: TaskResultItem[]
  total: number
  pages: number
  current_page: number
}

export interface TaskResultDetail extends TaskResultItem {
  parameters?: unknown
  result?: unknown
  error_message?: string | null
  presentation?: TaskResultPresentation
}

export interface C31ChildTaskSummary {
  task_id: string
  task_name: string
  spreadsheet_id: string
  sheet_name: string
  stock_code: string
  parameters: unknown[][]
  started: boolean
}

export interface C31BatchStartFailure {
  task_id: string
  task_name: string
  error: string
}

export interface C31BatchCreateResponse {
  status: string
  message?: string
  task_id: string
  task_ids: string[]
  started_task_ids: string[]
  failed_to_start: C31BatchStartFailure[]
  total_created: number
  total_started: number
  children: C31ChildTaskSummary[]
}

export interface XplJob {
  id: number
  task_id?: string | null
  task_result_id?: number | null
  return_series_id?: number | null
  status: string
  push_status?: string | null
  attempts?: number | null
  max_attempts?: number | null
  locked_by?: string | null
  error_message?: string | null
  load_elapsed_seconds?: number | null
  compute_elapsed_seconds?: number | null
  save_elapsed_seconds?: number | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface XplJobStatsMeta {
  oldest_pending_seconds?: number | null
  running_worker_count?: number
  avg_load_elapsed_seconds?: number | null
  avg_compute_elapsed_seconds?: number | null
  avg_save_elapsed_seconds?: number | null
  latest_finished_at?: string | null
}

export interface XplJobStats {
  pending?: number
  running?: number
  retrying?: number
  completed?: number
  error?: number
  cancelled?: number
  _meta?: XplJobStatsMeta
}

export interface XplJobListResponse {
  status: string
  items: XplJob[]
  pagination: PaginationState
}

export interface ModelSummaryColumn {
  key: string
  label: string
  format: 'percent' | 'number' | 'integer' | string
}

export interface ModelSummaryItem {
  id: number
  task_id: string
  task_result_id: number
  task_type: string
  task_name?: string | null
  stock_code?: string | null
  stock_name?: string | null
  model_key?: string | null
  model_name?: string | null
  year_label?: string | null
  period_key?: string | null
  kline_range?: string | null
  parameter_summary: Record<string, unknown>
  best_metric_name?: string | null
  best_metric_value?: number | null
  metrics: Record<string, string | number | null>
  is_best: boolean
  result_timestamp?: string | null
}

export interface ModelSummaryStatistics {
  stock_count: number
  cn_stock_count: number
  us_stock_count: number
  task_count: number
  return_beats_gt_0: number
  return_beats_gt_20: number
  return_beats_gt_50: number
  return_beats_gt_100: number
}

export interface ModelSummaryResponse {
  status: string
  summary_type: 'task' | 'stock'
  columns: ModelSummaryColumn[]
  summary: ModelSummaryStatistics
  items: ModelSummaryItem[]
  pagination: PaginationState
}

export interface ModelSummaryRebuildJob {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'error' | string
  progress?: number
  total?: number
  processed?: number
  message?: string | null
  error?: string | null
}

export interface ScheduledTask {
  id: number
  name: string
  description?: string | null
  cron_expression: string
  task_type: string
  task_function: string
  task_params: Record<string, unknown>
  is_active: boolean
  last_run_time?: string | null
  next_run_time?: string | null
  run_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface SchedulerStats {
  total_tasks: number
  active_tasks: number
  inactive_tasks: number
  scheduler_running: boolean
}

export interface SchedulerTaskListResponse {
  success: boolean
  tasks: ScheduledTask[]
  pagination: PaginationState
  message?: string
}

export interface SchedulerStatsResponse {
  success: boolean
  stats: SchedulerStats
  message?: string
}

export interface SchedulerTaskPayload {
  name: string
  description: string
  cron_expression: string
  task_type: string
  task_function: string
  task_params: string
  is_active: boolean
}
