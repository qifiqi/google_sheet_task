import { rawApi } from './index'

export const analyzePerformanceAnalysisV1 = (data) => rawApi.post('/performance_analysis/v1/analyze', data)

export const analyzePerformanceAnalysis = (data) => rawApi.post('/performance_analysis/analyze', data)

export const exportPerformanceAnalysisResult = (data) => rawApi.post('/api/exports/performance_analysis', data, {
  responseType: 'blob',
})

// V2 页 Word 报告导出（RPT-S/RPT-M），blob 下载（静态版走 fetch /api/exports/backtest-reports/word）
export const exportPerformanceAnalysisWordReport = (data) => rawApi.post('/api/exports/backtest-reports/word', data, {
  responseType: 'blob',
})
