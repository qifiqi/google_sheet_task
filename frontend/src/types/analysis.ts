export type AnalysisSource = 'backtest-training' | 'backtest-multi-product' | 'xpl-v1'

export type AnalysisRecord = Record<string, unknown>

export interface AnalysisMetric {
  key: string
  label: string
  format: 'percent' | 'number' | 'integer'
}

export interface AnalysisTableSection {
  key: string
  label: string
  rows: AnalysisRecord[]
}

export interface GlobalPreviewColumn {
  column_key: string
  header?: string
  result_id?: number
}

export interface GlobalPreviewRow {
  category?: string
  metric?: string
  index_value?: string
  values: Record<string, string>
}

export interface GlobalPreviewGroup {
  group_key: string
  group_label: string
  period?: string
  column_count?: number
  failed_results?: number
  columns: readonly GlobalPreviewColumn[]
  rows: readonly GlobalPreviewRow[]
}

export interface GlobalPreviewPayload {
  status: string
  task?: { id?: string; name?: string }
  summary?: Record<string, string | number>
  groups: readonly GlobalPreviewGroup[]
  products?: readonly { name?: string; code?: string; ratio?: string | number }[]
}

export interface WorksheetResponse {
  status: string
  worksheets?: string[]
  title?: string
  data?: {
    worksheets?: string[]
    title?: string
  }
}
