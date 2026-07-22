import { readonly, shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { AnalysisSource, GlobalPreviewPayload } from '../types/analysis'

type GlobalPreviewSource = Extract<AnalysisSource, 'backtest-training' | 'backtest-multi-product'>

export function useGlobalPreview(source: GlobalPreviewSource, taskId: string) {
  const payload = shallowRef<GlobalPreviewPayload | null>(null)
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  function endpoint(suffix = '') {
    const prefix = source === 'backtest-training' ? '/backtest-training' : '/backtest-multi-product'
    return `${prefix}/api/global-preview/${encodeURIComponent(taskId)}${suffix}`
  }

  async function load() {
    return request<GlobalPreviewPayload>(() => requestJson<GlobalPreviewPayload>(endpoint()))
  }

  async function calculateRatios(ratios: number[]) {
    return request<GlobalPreviewPayload>(() => requestJson<GlobalPreviewPayload>(endpoint('/calculate-ratios'), {
      method: 'POST',
      body: JSON.stringify({ ratios: ratios.map((ratio, productIndex) => ({ product_index: productIndex, ratio })) }),
    }))
  }

  async function saveRatios(ratios: number[]) {
    return request<GlobalPreviewPayload>(() => requestJson<GlobalPreviewPayload>(endpoint('/ratios'), {
      method: 'PUT',
      body: JSON.stringify({ ratios: ratios.map((ratio, productIndex) => ({ product_index: productIndex, ratio })) }),
    }))
  }

  async function request<T extends GlobalPreviewPayload>(factory: () => Promise<T>) {
    loading.value = true
    errorMessage.value = ''
    try {
      payload.value = await factory()
      return payload.value
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载全局预览失败'
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    payload: readonly(payload),
    loading: readonly(loading),
    errorMessage: readonly(errorMessage),
    load,
    calculateRatios,
    saveRatios,
    endpoint,
  }
}
