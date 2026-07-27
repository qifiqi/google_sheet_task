export interface GoogleSheetSelection {
  spreadsheetId: string
  title: string
  sheetName: string
}

export interface GoogleSheetExecutionSettings {
  tokenType: 'file' | 'json'
  tokenId: string
  tokenFile: string
  tokenJson: string
  proxyUrl: string
}

export interface GoogleSheetTokenOption {
  id: number
  name: string
  current_in_use_count: number
  task_usage_count: number
  max_usage_count: number
  is_available: boolean
}

export interface GoogleSheetCreateDraft {
  taskName: string
  description: string
  sheet: GoogleSheetSelection
  execution: GoogleSheetExecutionSettings
  parameters: string[]
}

export interface C31CreateDraft {
  taskName: string
  description: string
  stockCode: string
  marketType: 'cn' | 'en'
  priceMode: 'vwap_price' | 'kp_price' | 'sp_price'
  klineAdjustment: 'forward' | 'back' | 'none'
  endDate: string
  sheets: GoogleSheetSelection[]
  execution: GoogleSheetExecutionSettings
  parameters: string[]
}

export interface C4CreateDraft {
  taskName: string
  description: string
  sheets: GoogleSheetSelection[]
  execution: GoogleSheetExecutionSettings
  productCodes: string
  countMode: 'total' | 'n_plus_1'
  marketType: 'cn' | 'us'
  klineAdjustment: 'forward' | 'back' | 'none'
  dateRangeMode: Array<'full' | 'recent'>
  startDate: string
  endDate: string
}

export interface C57CreateDraft {
  taskName: string
  description: string
  sheets: GoogleSheetSelection[]
  execution: GoogleSheetExecutionSettings
  parameters: string[]
  klineSource: 'auto' | 'custom'
  countMode: 'total' | 'n_plus_1'
  priceMode: 'vwap_price' | 'kp_price' | 'sp_price'
  marketType: 'cn' | 'us'
  klineAdjustment: 'forward' | 'back' | 'none'
  dateRangeMode: Array<'full' | 'recent'>
  excludeRecentYears: number[]
  startDate: string
  endDate: string
}
