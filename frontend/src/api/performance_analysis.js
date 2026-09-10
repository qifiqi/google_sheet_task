import { rawApi } from './index'

export const analyzePerformanceAnalysisV1 = (data) => rawApi.post('/performance_analysis/v1/analyze', data)

export const exportPerformanceAnalysisResult = (data) => rawApi.post('/api/exports/performance_analysis', data, {
  responseType: 'blob',
})
