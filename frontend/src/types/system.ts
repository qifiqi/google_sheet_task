export interface SystemConfigItem {
  key: string
  value: string | null
  description: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface TokenUsageSummary {
  current_total_in_use: number
  current_total_usage: number
  global_max_usage: number
  available_token_count: number
}

export interface GoogleSheetToken {
  id: number
  name: string
  task_type: string
  token_context?: string
  token_context_size?: number
  task_usage_count: number
  current_in_use_count: number
  max_usage_count: number
  is_active: boolean
  is_available: boolean
  last_used_at?: string | null
}

export interface GoogleSheetItem {
  id: number
  name: string
  spreadsheet_id: string
  table_type: string
  remark?: string | null
  is_active: boolean
  is_in_use: boolean
  current_task_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminPermission {
  id: number
  code: string
  name: string
  group?: string | null
  description?: string | null
}

export interface AdminRole {
  id: number
  name: string
  code: string
  description?: string | null
  is_system: boolean
  permissions: AdminPermission[]
}

export interface AdminUser {
  id: number
  username: string
  mobile?: string | null
  is_active: boolean
  is_alert_oncall: boolean
  roles: AdminRole[]
  created_at?: string | null
  last_login?: string | null
}

export interface NavigationRegistryItem {
  id: number
  key: string
  label: string
  path?: string | null
  permission?: string | null
  parent_key?: string | null
  sort_order: number
  is_visible: boolean
}

export interface SystemLogEntry {
  timestamp?: string | null
  level: string
  message: string
  source?: string | null
}
