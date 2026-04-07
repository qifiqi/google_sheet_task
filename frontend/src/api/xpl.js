import { rawApi } from './index'

export const analyzeXplV1 = (data) => rawApi.post('/xpl/v1/analyze', data)

export const exportXplResult = (data) => rawApi.post('/xpl/export', data, {
  responseType: 'blob',
})
