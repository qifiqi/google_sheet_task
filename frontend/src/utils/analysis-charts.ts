import type { AnalysisRecord } from '../types/analysis'

export type AnalysisChartType = 'bar' | 'line'
export type AnalysisValueFormat = 'integer' | 'number' | 'percent'

export interface AnalysisChartSeries {
  color: string
  label: string
  type: AnalysisChartType
  values: Array<number | null>
}

export interface AnalysisChart {
  colorByValue?: boolean
  hasData: boolean
  key: string
  labels: string[]
  series: AnalysisChartSeries[]
  subtitle: string
  title: string
  valueFormat: AnalysisValueFormat
  wide?: boolean
  xAxisName: string
  yAxisName: string
}

const indexColor = '#2563EB'
const modelColor = '#10B981'
const dangerColor = '#EF4444'
const warningColor = '#F59E0B'
const violetColor = '#7C3AED'

export function buildAnalysisCharts(result?: AnalysisRecord): AnalysisChart[] {
  return [
    pairedChart('annual-return', '年度收益率', '指数 vs 模型', result, 'index_returns_rate', 'start_returns_rate', 'annual_return', '年度', '收益率 (%)', 'percent'),
    singleChart('annual-excess', '年超额收益', '模型 - 指数', result, 'excess_returns', 'annualized_return_diff', '年超额收益', '年度', '超额收益 (%)', 'percent', 'bar', true),
    pairedChart('annual-drawdown', '年度最大回撤', '指数 vs 模型', result, 'index_maximum_drawdown.year_maximum_drawdown', 'start_maximum_drawdown.year_maximum_drawdown', 'drawdown', '年度', '最大回撤 (%)', 'percent', dangerColor, warningColor),
    pairedChart('kama', '卡玛比率', '指数 vs 模型', result, 'index_kama_ratio', 'start_kama_ratio', 'kama_ratio', '年度', '卡玛比率', 'number'),
    pairedChart('sortino', '索提诺比例', '指数 vs 模型', result, 'index_sotino_ratio', 'start_sotino_ratio', 'sotino_ratio', '年度', '索提诺比例', 'number', indexColor, violetColor),
    scalarChart('monthly-volatility', '月收益率波动率', '指数 vs 模型', ['指数', '模型'], [result?.index_monthly_return_volatility, result?.start_monthly_return_volatility], '波动率 (%)', 'percent'),
    singleChart('monthly-excess', '月超额收益', '模型 - 指数', result, 'monthly_excess_returns', 'monthly_excess_return_diff', '月超额收益', '月份', '超额收益 (%)', 'percent', 'bar', true, true),
    sharpeChart(result),
    scalarChart('excess-metrics', '超额指标', '超额夏普 / 索提诺', ['超额夏普', '超额索提诺'], [result?.excess_sharp, result?.excess_of_promissory_note], '指标值', 'number'),
    scalarChart('repair-days', '最大回测修复天数', '指数 / 模型 / 超额', ['指数', '模型', '超额'], [result?.index_maximum_number_of_backtest_repair_days, result?.start_maximum_number_of_backtest_repair_days, result?.excess_maximum_number_of_backtest_repair_days], '天数', 'integer'),
    pairedChart('profit-monthly', '盈利月百分比', '指数 vs 模型', result, 'index_profit_monthly', 'start_profit_monthly', 'profit_monthly_percentage', '年度', '盈利月占比 (%)', 'percent'),
  ]
}

function pairedChart(key: string, title: string, subtitle: string, result: AnalysisRecord | undefined, indexPath: string, modelPath: string, valueKey: string, xAxisName: string, yAxisName: string, valueFormat: AnalysisValueFormat, indexSeriesColor = indexColor, modelSeriesColor = modelColor): AnalysisChart {
  const indexValues = toPeriodMap(recordsAtPath(result, indexPath), valueKey)
  const modelValues = toPeriodMap(recordsAtPath(result, modelPath), valueKey)
  const labels = sortedLabels([...indexValues.keys(), ...modelValues.keys()])
  return createChart(key, title, subtitle, labels, [
    series('指数', indexSeriesColor, 'line', labels.map((label) => indexValues.get(label) ?? null)),
    series('模型', modelSeriesColor, 'line', labels.map((label) => modelValues.get(label) ?? null)),
  ], xAxisName, yAxisName, valueFormat)
}

function singleChart(key: string, title: string, subtitle: string, result: AnalysisRecord | undefined, path: string, valueKey: string, label: string, xAxisName: string, yAxisName: string, valueFormat: AnalysisValueFormat, type: AnalysisChartType = 'line', colorByValue = false, wide = false): AnalysisChart {
  const values = toPeriodMap(recordsAtPath(result, path), valueKey)
  const labels = sortedLabels([...values.keys()])
  return createChart(key, title, subtitle, labels, [series(label, colorByValue ? warningColor : indexColor, type, labels.map((item) => values.get(item) ?? null))], xAxisName, yAxisName, valueFormat, colorByValue, wide)
}

function scalarChart(key: string, title: string, subtitle: string, labels: string[], rawValues: unknown[], yAxisName: string, valueFormat: AnalysisValueFormat): AnalysisChart {
  return createChart(key, title, subtitle, labels, [series(title, indexColor, 'bar', rawValues.map(toFiniteNumber))], '指标', yAxisName, valueFormat)
}

function sharpeChart(result?: AnalysisRecord): AnalysisChart {
  const indexValues = toSharpeMap(result?.index_sharpe_ratios)
  const modelValues = toSharpeMap(result?.start_sharpe_ratios)
  const labels = sortedLabels([...indexValues.keys(), ...modelValues.keys()])
  return createChart('sharpe', '夏普比率对比', '全周期 / 自然年 / 近年', labels, [
    series('指数夏普', indexColor, 'bar', labels.map((label) => indexValues.get(label) ?? null)),
    series('模型夏普', modelColor, 'bar', labels.map((label) => modelValues.get(label) ?? null)),
  ], '统计区间', '夏普比率', 'number', false, true)
}

function createChart(key: string, title: string, subtitle: string, labels: string[], chartSeries: AnalysisChartSeries[], xAxisName: string, yAxisName: string, valueFormat: AnalysisValueFormat, colorByValue = false, wide = false): AnalysisChart {
  return {
    key,
    title,
    subtitle,
    labels,
    series: chartSeries,
    xAxisName,
    yAxisName,
    valueFormat,
    colorByValue,
    wide,
    hasData: chartSeries.some((item) => item.values.some((value) => value !== null)),
  }
}

function series(label: string, color: string, type: AnalysisChartType, values: Array<number | null>): AnalysisChartSeries {
  return { label, color, type, values }
}

function recordsAtPath(result: AnalysisRecord | undefined, path: string): AnalysisRecord[] {
  if (!result) return []
  const value = path.split('.').reduce<unknown>((current, key) => isRecord(current) ? current[key] : undefined, result)
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function toPeriodMap(records: AnalysisRecord[], valueKey: string) {
  const result = new Map<string, number>()
  records.forEach((item) => {
    const label = String(item.year_month ?? item.year ?? item.date ?? '')
    const value = toFiniteNumber(item[valueKey])
    if (label && label.toLowerCase() !== 'all' && value !== null) result.set(label, value)
  })
  return result
}

function toSharpeMap(value: unknown) {
  const result = new Map<string, number>()
  if (!isRecord(value)) return result
  Object.entries(value).forEach(([key, item]) => {
    const ratio = isRecord(item) ? toFiniteNumber(item.sharpe_ratio) : null
    if (ratio !== null) result.set(formatSharpeLabel(key), ratio)
  })
  return result
}

function formatSharpeLabel(value: string) {
  if (value === 'all') return '全周期'
  const year = value.match(/^year_\d+_(\d{4})$/)
  if (year) return year[1]
  const recent = value.match(/^past_(\d+)_years/)
  return recent ? `近 ${recent[1]} 年` : value
}

function sortedLabels(values: string[]) {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right, 'zh-CN', { numeric: true }))
}

function toFiniteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
