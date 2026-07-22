import type { AnalysisMetric, AnalysisRecord, AnalysisTableSection } from '../types/analysis'

export const analysisMetrics: AnalysisMetric[] = [
  { key: 'outperform_year', label: '跑赢年份', format: 'percent' },
  { key: 'monthly_excess_volatility', label: '月超额波动率', format: 'number' },
  { key: 'excess_drawdown_winning_rate', label: '超额回撤胜率', format: 'percent' },
  { key: 'annualized_return_diff', label: '年超额收益', format: 'percent' },
  { key: 'index_profit_annual', label: '指数盈利年', format: 'percent' },
  { key: 'start_profit_annual', label: '模型盈利年', format: 'percent' },
  { key: 'index_monthly_return_volatility', label: '指数月波动率', format: 'number' },
  { key: 'start_monthly_return_volatility', label: '模型月波动率', format: 'number' },
]

const sectionLabels: Record<string, string> = {
  index_returns_rate: '年度收益率',
  start_returns_rate: '模型年度收益率',
  excess_returns: '超额收益',
  monthly_excess_returns: '月超额收益',
  kama: '卡玛比率',
  sotino: '索提诺比例',
  sharpe: '夏普比率',
  excess_metrics: '超额指标',
  repair_days: '回测修复天数',
  profit_statistics: '盈利统计',
  sheet_result: 'Sheet 结果',
  daily_returns: '日收益序列',
}

export function formatAnalysisValue(value: unknown, format: AnalysisMetric['format']) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  if (format === 'percent') return `${(number * 100).toFixed(2)}%`
  if (format === 'integer') return String(Math.round(number))
  return number.toFixed(4)
}

export function annualizedReturnDiff(result: AnalysisRecord) {
  const rows = result.excess_returns
  if (!Array.isArray(rows)) return null
  const all = rows.find((row) => isRecord(row) && String(row.year).toLowerCase() === 'all')
  return isRecord(all) ? all.annualized_return_diff : null
}

export function analysisTableSections(result: AnalysisRecord): AnalysisTableSection[] {
  return Object.entries(result)
    .filter(([key, value]) => sectionLabels[key] && (Array.isArray(value) || isRecord(value)))
    .map(([key, value]) => ({
      key,
      label: sectionLabels[key],
      rows: normalizeRows(value),
    }))
    .filter((section) => section.rows.length > 0)
}

export function analysisScalarRows(result: AnalysisRecord): AnalysisRecord[] {
  return Object.entries(result)
    .filter(([, value]) => !Array.isArray(value) && !isRecord(value))
    .map(([key, value]) => ({ key, value: formatCellValue(value) }))
}

export function analysisColumns(rows: AnalysisRecord[]) {
  return [...new Set(rows.flatMap((row) => Object.keys(row)))].slice(0, 14)
}

export function analysisRowsForSource(result: AnalysisRecord, sourceKey: string): AnalysisRecord[] {
  const value = result[sourceKey]
  if (Array.isArray(value)) {
    return value.map((item, index) => isRecord(item) ? item : { index: index + 1, value: formatCellValue(item) })
  }
  if (!isRecord(value)) return []
  return Object.entries(value).map(([key, item]) => isRecord(item) ? { key, ...item } : { key, value: formatCellValue(item) })
}

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(6)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function normalizeRows(value: unknown): AnalysisRecord[] {
  if (Array.isArray(value)) {
    return value.map((item, index) => isRecord(item) ? item : { index: index + 1, value: formatCellValue(item) })
  }
  if (!isRecord(value)) return []
  return Object.entries(value).map(([key, item]) => ({ key, value: formatCellValue(item) }))
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
