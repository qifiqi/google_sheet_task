import { shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { GoogleSheetToken, SystemConfigItem, TokenUsageSummary } from '../types/system'

const EMPTY_TOKEN_SUMMARY: TokenUsageSummary = {
  current_total_in_use: 0,
  current_total_usage: 0,
  global_max_usage: 0,
  available_token_count: 0,
}

export function useSystemConfig() {
  const configs = shallowRef<SystemConfigItem[]>([])
  const tokens = shallowRef<GoogleSheetToken[]>([])
  const tokenSummary = shallowRef<TokenUsageSummary>({ ...EMPTY_TOKEN_SUMMARY })
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  async function loadConfigs() {
    loading.value = true
    errorMessage.value = ''
    try {
      const configPayload = await requestJson<{ status: string; configs: SystemConfigItem[] }>('/api/system-configs')
      if (configPayload.status !== 'success') throw new Error('加载系统配置失败')
      configs.value = configPayload.configs || []
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载系统配置失败'
    } finally {
      loading.value = false
    }
  }

  async function loadTokens() {
    loading.value = true
    errorMessage.value = ''
    try {
      const tokenPayload = await requestJson<{ status: string; tokens: GoogleSheetToken[]; summary: TokenUsageSummary }>('/api/google-sheet-tokens')
      if (tokenPayload.status !== 'success') throw new Error('加载 Token 池失败')
      tokens.value = tokenPayload.tokens || []
      tokenSummary.value = tokenPayload.summary || { ...EMPTY_TOKEN_SUMMARY }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载 Token 池失败'
    } finally {
      loading.value = false
    }
  }

  async function load() { await Promise.all([loadConfigs(), loadTokens()]) }

  async function updateConfig(item: Pick<SystemConfigItem, 'key' | 'value' | 'description'>) {
    await requestJson(`/api/system-configs/${encodeURIComponent(item.key)}`, {
      method: 'PUT', body: JSON.stringify({ value: item.value || '', description: item.description || '' }),
    })
    await loadConfigs()
  }

  async function validate() {
    return requestJson<{ status: string; validation: Record<string, unknown> }>('/api/config/validate')
  }

  async function importToken(payload: { name: string; task_type: string; max_usage_count: number; token_context: string }) {
    await requestJson('/api/google-sheet-tokens/import', { method: 'POST', body: JSON.stringify(payload) })
    await loadTokens()
  }

  async function getToken(tokenId: number) {
    const payload = await requestJson<{ status: string; token: GoogleSheetToken }>(`/api/google-sheet-tokens/${tokenId}?include_context=1`)
    return payload.token
  }

  async function updateToken(token: GoogleSheetToken) {
    await requestJson(`/api/google-sheet-tokens/${token.id}`, {
      method: 'PUT', body: JSON.stringify({ name: token.name, task_type: token.task_type, max_usage_count: token.max_usage_count, is_active: token.is_active, token_context: token.token_context }),
    })
    await loadTokens()
  }

  async function removeToken(tokenId: number) {
    await requestJson(`/api/google-sheet-tokens/${tokenId}`, { method: 'DELETE' })
    await loadTokens()
  }

  return { configs, tokens, tokenSummary, loading, errorMessage, load, loadConfigs, loadTokens, updateConfig, validate, importToken, getToken, updateToken, removeToken }
}
