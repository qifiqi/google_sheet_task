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
  roles?: UserRole[]
  permissions?: string[]
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
  children?: NavItem[]
}

export interface DashboardOverview {
  success: boolean
  summary?: Record<string, number>
  status_distribution?: Array<{ status: string; count: number }>
  task_type_distribution?: Array<{ task_type: string; count: number }>
  daily_trend?: Array<Record<string, unknown>>
  recent_tasks?: Array<Record<string, unknown>>
  active_tasks?: Array<Record<string, unknown>>
  checked_at?: string
}
