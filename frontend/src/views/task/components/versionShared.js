// C4/C5/C7 任务详情的版本共享逻辑（迁移自老静态页，非重设计）。
// 结果分组：static/js/pages/google_sheet_c{4,5,7}_detail.js 的 groupResults/adaptC7ResultMetrics。
// 指标映射：同文件 metricDisplayNameMap + normalizeLegacyC7MetricValue。
// 配置展示：static/js/common/business/config-edit.js 的 formatConfigDisplayValue 系列函数。
// 同名同语义翻译，取值口径以老文件为准；页面差异经 version 参数（'c4' | 'c5' | 'c7'）表达。

// ── 基础判别 / 取值（对齐 google_sheet_detail.js 同名函数，各版本页共用）──

export function isPlainObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

export function getFlatResult(metrics) {
  if (!isPlainObject(metrics)) {
    return null
  }
  return isPlainObject(metrics.flat_result) ? metrics.flat_result : null
}

export function getPreferredMetricValue(metrics, key) {
  const flatResult = getFlatResult(metrics)
  if (flatResult && flatResult[key] != null) {
    return flatResult[key]
  }
  return metrics && metrics[key] != null ? metrics[key] : null
}

export function getFirstMetricValue(source, keys) {
  if (!isPlainObject(source)) {
    return null
  }
  for (const key of keys) {
    if (source[key] != null) {
      return source[key]
    }
  }
  return null
}

export function getModelSharpeValue(metrics, type) {
  const flatResult = getFlatResult(metrics)

  if (flatResult) {
    if (type === 'index') {
      return getFirstMetricValue(flatResult, ['index_sharpe_ratio', 'index_sharp', 'ixpl', 'i_xpl', 'index_xpl'])
    }
    return getFirstMetricValue(flatResult, ['start_sharpe_ratio', 'start_sharp', 'sxpl', 's_xpl', 'start_xpl'])
  }

  const legacyPerformanceAnalysis = type === 'index'
    ? (metrics.index_return_xpl || {})
    : (metrics.start_return_xpl || {})
  return legacyPerformanceAnalysis.sharpe_ratio != null ? legacyPerformanceAnalysis.sharpe_ratio : null
}

export function shouldShowDetailMetric(key) {
  return !['start_return_xpl', 'index_return_xpl', 'analyze_result'].includes(String(key))
}

// ── 指标格式化 ──

export function parseMetricKey(key) {
  const m = String(key).match(/^([A-Za-z_]+)(\d+)?$/)
  if (m) {
    return { prefix: m[1], num: m[2] != null ? parseInt(m[2], 10) : null }
  }
  return { prefix: String(key), num: null }
}

// 指标 key 排序：D* 优先，其次按前缀分组和数字顺序（c4/c5/c7 同款）
export function sortMetricKeys(keys) {
  return keys.slice().sort((a, b) => {
    const pa = parseMetricKey(a)
    const pb = parseMetricKey(b)

    const aIsD = pa.prefix === 'D'
    const bIsD = pb.prefix === 'D'
    if (aIsD && !bIsD) return -1
    if (!aIsD && bIsD) return 1

    if (pa.prefix !== pb.prefix) {
      return pa.prefix.localeCompare(pb.prefix)
    }
    if (pa.num !== null && pb.num !== null) {
      return pa.num - pb.num
    }
    return String(a).localeCompare(String(b))
  })
}

export function formatMetricRawValue(value, digits) {
  if (value == null || value === '') {
    return null
  }
  const numericValue = Number(value)
  if (Number.isFinite(numericValue)) {
    return typeof digits === 'number' ? numericValue.toFixed(digits) : String(numericValue)
  }
  return value
}

// C7 历史数据值格式归一（c7_detail.js:1211-1230 原样翻译）
const c7RawPercentMetricKeys = new Set(['D10', 'D15', 'D18', 'D19'])
const c7LeveragePercentMetricKeys = new Set(['D22', 'D24', 'D25'])

export function normalizeLegacyC7MetricValue(value, key) {
  const metricKey = String(key || '')
  if (value == null || value === '') {
    return value
  }

  const text = String(value).trim()
  if (c7RawPercentMetricKeys.has(metricKey) && !text.endsWith('%')) {
    const numericValue = Number(text.replace(/,/g, ''))
    return Number.isFinite(numericValue) ? `${(numericValue * 100).toFixed(2)}%` : value
  }
  if (c7LeveragePercentMetricKeys.has(metricKey) && text.endsWith('%')) {
    const numericValue = Number(text.slice(0, -1))
    return Number.isFinite(numericValue) ? numericValue / 100 : value
  }
  return value
}

// digits 精度格式化；C7 键带归一（c4/c5 不传 key，行为不变）
export function formatMetricText(value, digits, key = null) {
  const normalized = key ? normalizeLegacyC7MetricValue(value, key) : value
  const formatted = formatMetricRawValue(normalized, digits)
  if (formatted == null) {
    return '-'
  }
  return String(formatted)
}

// ── 指标显示名映射（各版本页 metricDisplayNameMap 原样抄录，公共尾部合并）──

const versionCommonMetricNames = {
  annualized_return_diff: '年化超额收益',
  avg_monthly_excess_returns: '平均月超额',
  excess_drawdown_winning_rate: '超额回撤胜率',
  excess_maximum_number_of_backtest_repair_days: '超额最大修复天数',
  excess_sortino: '超额索提诺',
  excess_sharpe: '超额夏普',
  index_annual_std_dev: '指数年化波动率',
  index_annualized_return: '指数年化收益',
  index_avg_monthly_return: '指数平均月收益率',
  index_avg_monthly_return_common: '指数平均月收益率',
  index_kama_ratio: '指数卡玛比率',
  index_monthly_return_volatility: '指数月收益率波动率',
  index_monthly_std_dev: '指数月度标准差',
  index_profit_annual: '指数盈利年份百分比',
  index_profit_monthly_percentage: '指数月盈利百分比',
  index_sharpe_ratio: '指数夏普比率',
  index_sortino_ratio: '指数索提诺比率',
  max_drawdown: '年最大超额回撤',
  monthly_excess_return_percentage_last_return: '月超额收益胜率',
  monthly_excess_volatility: '月超额波动率',
  outperform_year: '跑赢年份(百分比)',
  start_annual_std_dev: '模型年化波动率',
  start_annualized_return: '模型年化收益',
  start_avg_monthly_return: '模型平均月收益率',
  start_avg_monthly_return_common: '模型平均月收益率',
  start_drawdown: '年最大回撤',
  start_kama_ratio: '模型卡玛比率',
  start_maximum_number_of_backtest_repair_days: '最大修复天数',
  start_monthly_return_volatility: '模型月收益率波动率',
  start_monthly_std_dev: '模型月度标准差',
  start_profit_annual: '模型盈利年份百分比',
  start_profit_monthly_percentage: '模型月盈利百分比',
  start_sharpe_ratio: '模型夏普比率',
  start_sortino_ratio: '模型索提诺比率'
}

// C4/C5：汇总指标位于 D2-D20
export const c4C5MetricDisplayNameMap = {
  D2: 'Return%',
  D3: 'Annualized',
  D4: 'Max DD%',
  D5: 'Index Return',
  D6: 'Annualized',
  D7: 'Index max dd',
  D8: 'Fee total',
  D9: 'Fee annualized',
  D10: '年换手率',
  D11: 'return beats',
  D12: 'ddBeats',
  D13: 'max(1y beats%)',
  D14: 'min(1y beats%)',
  D15: '最大理论杠杆率',
  D16: '平均理论杠杆率',
  D17: '单位理论杠杆率收益',
  D18: '最大实际杠杆率',
  D19: '平均实际杠杆率',
  D20: '单位实际杠杆率收益',
  ...versionCommonMetricNames
}

// C7：汇总指标位于 D8-D26
export const c7MetricDisplayNameMap = {
  D8: 'Return%',
  D9: 'Annualized',
  D10: 'Max DD%',
  D11: 'Index Return',
  D12: 'Annualized',
  D13: 'Index max dd',
  D14: 'Fee total',
  D15: 'Fee annualized',
  D16: '年换手率',
  D17: 'return beats',
  D18: 'ddBeats',
  D19: 'max(1y beats%)',
  D20: 'min(1y beats%)',
  D21: '最大理论杠杆率',
  D22: '平均理论杠杆率',
  D23: '单位理论杠杆率收益',
  D24: '最大实际杠杆率',
  D25: '平均实际杠杆率',
  D26: '单位实际杠杆率收益',
  ...versionCommonMetricNames
}

export function getMetricDisplayLabel(key, version) {
  const map = version === 'c7' ? c7MetricDisplayNameMap : c4C5MetricDisplayNameMap
  const rawKey = String(key)
  return map[rawKey] || rawKey
}

// 分组卡片表头指标列（模型标题后的 D2~D7 / D8~D13 六个取数位）
export const VERSION_METRIC_COLUMNS = {
  c4: [
    { key: 'D2', label: 'Return' },
    { key: 'D3', label: 'Annualized' },
    { key: 'D4', label: 'Max DD%' },
    { key: 'D5', label: 'Index Return' },
    { key: 'D6', label: 'Annualized' },
    { key: 'D7', label: 'Index max dd' }
  ],
  c5: [
    { key: 'D2', label: 'Return' },
    { key: 'D3', label: 'Annualized' },
    { key: 'D4', label: 'Max DD%' },
    { key: 'D5', label: 'Index Return' },
    { key: 'D6', label: 'Annualized' },
    { key: 'D7', label: 'Index max dd' }
  ],
  c7: [
    { key: 'D8', label: 'Return' },
    { key: 'D9', label: 'Annualized' },
    { key: 'D10', label: 'Max DD%' },
    { key: 'D11', label: 'Index Return' },
    { key: 'D12', label: 'Annualized' },
    { key: 'D13', label: 'Index max dd' }
  ]
}

// ── C7.0.3 适配（c7_detail.js:428-457 原样翻译）──

// sheets[].c7_model_version 含 c7_0_3 时按旧取数位（D2-D20）重映射到 D8-D26
export function isC7V03Config(config) {
  return Array.isArray(config?.sheets)
    && config.sheets.some((sheet) => sheet?.c7_model_version === 'c7_0_3')
}

export function adaptC7ResultMetrics(metrics, c7V03) {
  if (!isPlainObject(metrics) || !c7V03) {
    return metrics
  }

  const adapted = { ...metrics }
  for (let row = 2; row <= 20; row += 1) {
    delete adapted[`D${row}`]
  }
  for (let offset = 0; offset <= 18; offset += 1) {
    const sourceKey = `D${offset + 2}`
    if (metrics[sourceKey] != null) {
      adapted[`D${offset + 8}`] = metrics[sourceKey]
    }
  }
  return adapted
}

// ── 结果分组（c4/c5_detail.js:380-455 与 c7_detail.js:460-540 的合并翻译）──

function computeKlineRange(params) {
  if (!Array.isArray(params.kline) || params.kline.length === 0) {
    return '-'
  }
  const sortedKline = params.kline
    .filter((r) => r && r.stock_date)
    .slice()
    .sort((a, b) => (a.stock_date > b.stock_date ? 1 : -1))
  if (sortedKline.length === 0) {
    return '-'
  }
  const first = sortedKline[0]
  const last = sortedKline[sortedKline.length - 1]
  return `${first.stock_date || '-'} ~ ${last.stock_date || '-'}`
}

// 按每条 result（参数组合）分组，组内一个模型一行；C7 先按模型版本做取数位适配。
// c4/c5 的 D2~D7 走 getPreferredMetricValue（flat_result 优先），c7 读适配后的 rawMetrics
//（与老 renderResults 的取数口径逐字对齐）。
export function buildVersionResultGroups(version, resultsArray, taskConfig) {
  const list = []
  if (!Array.isArray(resultsArray)) {
    return list
  }

  const c7V03 = version === 'c7' && isC7V03Config(taskConfig)
  const metricKeys = (VERSION_METRIC_COLUMNS[version] || VERSION_METRIC_COLUMNS.c4).map((col) => col.key)

  resultsArray.forEach((item) => {
    const params = item.parameters || {}
    const stockCode = params.stock_code || '-'
    const klineRange = computeKlineRange(params)
    const a1 = params.A1 != null ? params.A1 : null
    const b1 = params.B1 != null ? params.B1 : null

    const resultObj = item.result && typeof item.result === 'object' ? item.result : {}
    const models = []

    Object.keys(resultObj).forEach((keyName) => {
      const metrics = version === 'c7'
        ? adaptC7ResultMetrics(resultObj[keyName] || {}, c7V03)
        : (resultObj[keyName] || {})

      // 卡片六列取值：c4/c5 = preferred（d2~d7），c7 = rawMetrics 上直接取
      const displayValues = {}
      metricKeys.forEach((metricKey, idx) => {
        displayValues[metricKey] = version === 'c7'
          ? metrics[metricKey]
          : getPreferredMetricValue(metrics, metricKeys[idx])
      })

      models.push({
        modelKey: keyName,
        modelCode: String(keyName).split('__')[0] || String(keyName),
        modelTitle: String(keyName).split('__').slice(1).join('__'),
        displayValues,
        startSharpe: getModelSharpeValue(metrics, 'start'),
        indexSharpe: getModelSharpeValue(metrics, 'index'),
        rawMetrics: metrics
      })
    })

    list.push({
      stepIndex: item.step_index,
      success: !!item.success,
      errorMessage: item.error_message || null,
      timestamp: item.timestamp || null,
      taskId: item.task_id || null,
      rowId: item.id != null ? item.id : null,
      parameters: params,
      stockCode,
      a1,
      b1,
      klineRange,
      models
    })
  })

  return list
}

// 夏普列展示文本（老 renderResults 的 indexSharpeText / strategySharpeText）
export function formatSharpeText(value) {
  if (value == null) return '-'
  const v = Number(value)
  return Number.isFinite(v) ? v.toFixed(6) : String(value)
}

// ── 配置展示格式化（config-edit.js formatConfigDisplayValue 系列原样翻译）──

export function formatConfigDisplayValue(value, mapping) {
  if (Array.isArray(value)) {
    const formatted = value
      .map((item) => formatConfigDisplayValue(item, mapping))
      .filter(Boolean)
    return formatted.length ? formatted.join('、') : '-'
  }

  if (value === null || value === undefined || value === '') {
    return '-'
  }

  const normalized = String(value)
  return mapping && mapping[normalized] ? mapping[normalized] : normalized
}

export function formatCountMode(value) {
  return formatConfigDisplayValue(value, { total: '总数', n_plus_1: 'N+1' })
}

export function formatDateRangeMode(value) {
  return formatConfigDisplayValue(value, { full: '整年', recent: '近年' })
}

export function formatMarketType(value) {
  return formatConfigDisplayValue(value, { cn: 'A股', us: '美股' })
}

export function formatTokenType(value) {
  return formatConfigDisplayValue(value, { file: 'Token 文件', json: 'Token JSON' })
}

export function formatPriceMode(value) {
  return formatConfigDisplayValue(value, {
    kp_price: '开盘价',
    sp_price: '收盘价',
    vwap_price: '加权平均价'
  })
}

export function formatTokenSelectionMode(value) {
  return formatConfigDisplayValue(value, { __random__: '随机 Token' })
}

// 移除的近年区间（c7_detail.js formatExcludedYears：0.5 = 近半年）
export function formatExcludedYears(value) {
  if (!value || !Array.isArray(value) || value.length === 0) {
    return '无'
  }
  return value.map((y) => (Number(y) === 0.5 ? '近半年' : `近${y}年`)).join('、')
}

// ── 执行时长（老 detail.js formatDuration + created_at→(end_time||now) 口径，补天档）──

export function formatExecutionDuration(seconds) {
  if (seconds == null) {
    return '-'
  }
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) {
    return `${s}秒`
  }
  if (s < 3600) {
    return `${Math.floor(s / 60)}分${s % 60}秒`
  }
  if (s < 86400) {
    return `${Math.floor(s / 3600)}小时${Math.floor((s % 3600) / 60)}分钟`
  }
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  return `${days}天${hours}小时${minutes}分钟`
}
