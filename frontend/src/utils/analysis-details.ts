import type { AnalysisRecord } from '../types/analysis'

export type DetailValueFormat = 'date' | 'integer' | 'number' | 'percent' | 'text'

export interface AnalysisDetailColumn {
  format?: DetailValueFormat
  key: string
  label: string
  minWidth?: number
}

export interface AnalysisDetailSection {
  columns: AnalysisDetailColumn[]
  label: string
  name: string
  rows: AnalysisRecord[]
}

export function buildAnalysisDetails(result?: AnalysisRecord): AnalysisDetailSection[] {
  return [
    annualSection(result),
    excessSection(result),
    monthlyExcessSection(result),
    pairedMetricSection('kama', '卡玛比率', result, 'index_kama_ratio', 'start_kama_ratio', 'kama_ratio', '卡玛比率', ['annualized_return', 'drawdown']),
    pairedMetricSection('sortino', '索提诺比例', result, 'index_sotino_ratio', 'start_sotino_ratio', 'sotino_ratio', '索提诺比例', ['average_monthly_annualized_return', 'downside_standard_deviation']),
    sharpeSection(result),
    excessMetricSection(result),
    repairDaysSection(result),
    profitSection(result),
    sheetResultSection(result),
  ]
}

export function formatDetailValue(value: unknown, format: DetailValueFormat = 'text') {
  if (value === null || value === undefined || value === '') return '-'
  if (format === 'date') return String(value)
  const number = Number(value)
  if (format === 'percent' && Number.isFinite(number)) return `${(number * 100).toFixed(2)}%`
  if (format === 'integer' && Number.isFinite(number)) return String(Math.round(number))
  if (format === 'number' && Number.isFinite(number)) return number.toFixed(4)
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function annualSection(result?: AnalysisRecord): AnalysisDetailSection {
  const indexReturns = records(result?.index_returns_rate)
  const modelReturns = records(result?.start_returns_rate)
  const indexDrawdowns = recordsAt(result, 'index_maximum_drawdown.year_maximum_drawdown')
  const modelDrawdowns = recordsAt(result, 'start_maximum_drawdown.year_maximum_drawdown')
  const years = sortedYears([indexReturns, modelReturns, indexDrawdowns, modelDrawdowns])
  return {
    name: 'annual', label: '年度收益/回撤',
    columns: [
      column('year', '年度'), column('index_annual_return', '指数收益', 'percent'), column('model_annual_return', '模型收益', 'percent'), column('index_drawdown', '指数回撤', 'percent'), column('model_drawdown', '模型回撤', 'percent'), column('index_drawdown_date', '指数回撤日期', 'date', 150), column('model_drawdown_date', '模型回撤日期', 'date', 150),
    ],
    rows: years.map((year) => ({
      year,
      index_annual_return: byYear(indexReturns, year)?.annual_return,
      model_annual_return: byYear(modelReturns, year)?.annual_return,
      index_drawdown: byYear(indexDrawdowns, year)?.drawdown,
      model_drawdown: byYear(modelDrawdowns, year)?.drawdown,
      index_drawdown_date: byYear(indexDrawdowns, year)?.date,
      model_drawdown_date: byYear(modelDrawdowns, year)?.date,
    })),
  }
}

function excessSection(result?: AnalysisRecord): AnalysisDetailSection {
  return {
    name: 'excess', label: '超额收益',
    columns: [column('year', '年度'), column('start_annualized_return', '模型年化', 'percent'), column('index_annualized_return', '指数年化', 'percent'), column('annualized_return_diff', '超额收益', 'percent'), column('start_end_date', '回测区间', 'date', 290)],
    rows: records(result?.excess_returns),
  }
}

function monthlyExcessSection(result?: AnalysisRecord): AnalysisDetailSection {
  return {
    name: 'monthly-excess', label: '月超额收益',
    columns: [column('year_month', '月份'), column('index_monthly_return', '指数月收益', 'percent'), column('start_monthly_return', '模型月收益', 'percent'), column('monthly_excess_return_diff', '超额收益', 'percent'), column('date', '统计日期', 'date', 140)],
    rows: records(result?.monthly_excess_returns),
  }
}

function pairedMetricSection(name: string, label: string, result: AnalysisRecord | undefined, indexKey: string, modelKey: string, metricKey: string, metricLabel: string, supportingKeys: string[]): AnalysisDetailSection {
  const indexRows = records(result?.[indexKey])
  const modelRows = records(result?.[modelKey])
  const columns = [column('year', '年度'), column('index_metric', `指数${metricLabel}`, 'number'), column('model_metric', `模型${metricLabel}`, 'number')]
  supportingKeys.forEach((key) => {
    columns.push(column(`index_${key}`, `指数${supportingLabel(key)}`, key.includes('drawdown') ? 'percent' : 'number'))
    columns.push(column(`model_${key}`, `模型${supportingLabel(key)}`, key.includes('drawdown') ? 'percent' : 'number'))
  })
  return {
    name,
    label,
    columns,
    rows: sortedYears([indexRows, modelRows]).map((year) => {
      const indexRow = byYear(indexRows, year)
      const modelRow = byYear(modelRows, year)
      return {
        year,
        index_metric: indexRow?.[metricKey],
        model_metric: modelRow?.[metricKey],
        ...Object.fromEntries(supportingKeys.flatMap((key) => [[`index_${key}`, indexRow?.[key]], [`model_${key}`, modelRow?.[key]]])),
      }
    }),
  }
}

function sharpeSection(result?: AnalysisRecord): AnalysisDetailSection {
  const indexRows = recordsFromObject(result?.index_sharpe_ratios)
  const modelRows = recordsFromObject(result?.start_sharpe_ratios)
  const periods = sortedText([...indexRows.keys(), ...modelRows.keys()])
  return {
    name: 'sharpe', label: '夏普比率',
    columns: [column('period', '统计区间', 'text', 160), column('index_sharpe', '指数夏普', 'number'), column('model_sharpe', '模型夏普', 'number'), column('index_annual_std_dev', '指数年波动', 'percent'), column('model_annual_std_dev', '模型年波动', 'percent'), column('index_avg_monthly_return', '指数月均收益', 'percent'), column('model_avg_monthly_return', '模型月均收益', 'percent'), column('range', '统计范围', 'date', 180)],
    rows: periods.map((period) => {
      const indexRow = indexRows.get(period)
      const modelRow = modelRows.get(period)
      return {
        period: formatSharpePeriod(period),
        index_sharpe: indexRow?.sharpe_ratio,
        model_sharpe: modelRow?.sharpe_ratio,
        index_annual_std_dev: indexRow?.annual_std_dev,
        model_annual_std_dev: modelRow?.annual_std_dev,
        index_avg_monthly_return: indexRow?.avg_monthly_return,
        model_avg_monthly_return: modelRow?.avg_monthly_return,
        range: indexRow?.start_date && indexRow?.end_date ? `${indexRow.start_date} / ${indexRow.end_date}` : '-',
      }
    }),
  }
}

function excessMetricSection(result?: AnalysisRecord): AnalysisDetailSection {
  const rows = [
    ['excess_sharp', '超额夏普', result?.excess_sharp, 'number'],
    ['excess_of_promissory_note', '超额索提诺', result?.excess_of_promissory_note, 'number'],
    ['excess_drawdown_winning_rate', '超额回撤胜率', result?.excess_drawdown_winning_rate, 'percent'],
    ['monthly_excess_volatility', '月超额波动率', result?.monthly_excess_volatility, 'percent'],
    ['outperform_year', '跑赢年份占比', result?.outperform_year, 'percent'],
  ]
  return {
    name: 'excess-metrics', label: '超额指标',
    columns: [column('key', '指标'), column('label', '名称'), column('value', '数值', 'number'), column('format', '格式')],
    rows: rows.filter(([, , value]) => value !== undefined).map(([key, label, value, format]) => ({ key, label, value, format })),
  }
}

function repairDaysSection(result?: AnalysisRecord): AnalysisDetailSection {
  return {
    name: 'repair-days', label: '回测修复天数',
    columns: [column('key', '指标'), column('label', '数据组'), column('value', '最大修复天数', 'integer')],
    rows: [
      { key: 'index_maximum_number_of_backtest_repair_days', label: '指数', value: result?.index_maximum_number_of_backtest_repair_days },
      { key: 'start_maximum_number_of_backtest_repair_days', label: '模型', value: result?.start_maximum_number_of_backtest_repair_days },
      { key: 'excess_maximum_number_of_backtest_repair_days', label: '超额', value: result?.excess_maximum_number_of_backtest_repair_days },
    ].filter((row) => row.value !== undefined),
  }
}

function profitSection(result?: AnalysisRecord): AnalysisDetailSection {
  const indexRows = records(result?.index_profit_monthly)
  const modelRows = records(result?.start_profit_monthly)
  const years = sortedYears([indexRows, modelRows])
  return {
    name: 'profit', label: '盈利统计',
    columns: [column('year', '年度'), column('index_profit_monthly_percentage', '指数盈利月占比', 'percent'), column('model_profit_monthly_percentage', '模型盈利月占比', 'percent'), column('index_profit_annual', '指数盈利年', 'integer'), column('model_profit_annual', '模型盈利年', 'integer')],
    rows: years.map((year) => ({
      year,
      index_profit_monthly_percentage: byYear(indexRows, year)?.profit_monthly_percentage,
      model_profit_monthly_percentage: byYear(modelRows, year)?.profit_monthly_percentage,
      index_profit_annual: year === 'all' ? result?.index_profit_annual : undefined,
      model_profit_annual: year === 'all' ? result?.start_profit_annual : undefined,
    })),
  }
}

function sheetResultSection(result?: AnalysisRecord): AnalysisDetailSection {
  const sheet = isRecord(result?.sheet_result) ? result?.sheet_result : {}
  return {
    name: 'sheet-result', label: 'Sheet 结果',
    columns: [column('key', '字段'), column('value', '值', 'text', 260)],
    rows: Object.entries(sheet).map(([key, value]) => ({ key, value })),
  }
}

function column(key: string, label: string, format: DetailValueFormat = 'text', minWidth = 130): AnalysisDetailColumn {
  return { key, label, format, minWidth }
}

function records(value: unknown): AnalysisRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function recordsAt(result: AnalysisRecord | undefined, path: string): AnalysisRecord[] {
  const value = path.split('.').reduce<unknown>((current, key) => isRecord(current) ? current[key] : undefined, result)
  return records(value)
}

function recordsFromObject(value: unknown) {
  const output = new Map<string, AnalysisRecord>()
  if (!isRecord(value)) return output
  Object.entries(value).forEach(([key, item]) => { if (isRecord(item)) output.set(key, item) })
  return output
}

function byYear(rows: AnalysisRecord[], year: string) {
  return rows.find((row) => String(row.year) === year)
}

function sortedYears(groups: AnalysisRecord[][]) {
  return sortedText(groups.flatMap((items) => items.map((item) => String(item.year ?? ''))).filter(Boolean))
}

function sortedText(values: string[]) {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right, 'zh-CN', { numeric: true }))
}

function formatSharpePeriod(value: string) {
  if (value === 'all') return '全周期'
  const year = value.match(/^year_\d+_(\d{4})$/)
  if (year) return year[1]
  const recent = value.match(/^past_(\d+)_years/)
  return recent ? `近 ${recent[1]} 年` : value
}

function supportingLabel(key: string) {
  const labels: Record<string, string> = {
    annualized_return: '年化收益',
    average_monthly_annualized_return: '月均年化收益',
    downside_standard_deviation: '下行标准差',
    drawdown: '最大回撤',
  }
  return labels[key] || key
}

function isRecord(value: unknown): value is AnalysisRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
