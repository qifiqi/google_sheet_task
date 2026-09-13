import { rawApi } from './index'

export const analyzePerformanceAnalysisV1 = (data, config) => rawApi.post('/performance_analysis/v1/analyze', data, config)

export const analyzePerformanceAnalysis = (data, config) => rawApi.post('/performance_analysis/analyze', data, config)

export const exportPerformanceAnalysisResult = (data) => rawApi.post('/api/exports/performance_analysis', data, {
  responseType: 'blob',
})

// V2 页 Word 报告导出（RPT-S/RPT-M）：返回原始 Response，供调用方解析
// Content-Disposition 文件名（blob 拦截器拿不到响应头；静态版 v2.js 同样走原始 Response）。
export async function exportPerformanceAnalysisWordReportResponse(data) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch('/api/exports/backtest-reports/word', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
  })
  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}))
    throw new Error(errData.message || `请求失败: ${resp.status}`)
  }
  return resp
}

// Word 报告弹窗的股票搜索：透传 signal 支持 AbortController 丢弃过期响应
// （端点与 api/backtest.js 的 searchStocks 相同，该文件签名不支持 signal）。
export const searchStocksWithSignal = (params, { signal } = {}) => rawApi.get('/api/search-stocks', { params, signal })

// 权重组合分析：POST NDJSON 流（每行一个组合 JSON），onRow 逐行回调，返回解析总行数。
// 服务端逐组合流式输出，行数可达数千，必须边收边解析；错误行形如 {"error":true,"message":...}。
export async function analyzeWeightCombinationStream(payload, { onRow, signal } = {}) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch('/performance_analysis/v1/weight_combination', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  })
  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}))
    throw new Error(errData.message || `请求失败: ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let count = 0

  const handleLine = (line) => {
    if (!line.trim()) return
    let data
    try {
      data = JSON.parse(line)
    } catch {
      // 与静态版一致：坏行容忍跳过，不中断整体流
      console.error('解析 JSON 失败:', line)
      return
    }
    if (data.error) throw new Error(data.message || '服务端返回错误')
    onRow?.(data)
    count++
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) handleLine(line)
  }
  if (buffer) handleLine(buffer)

  return count
}
