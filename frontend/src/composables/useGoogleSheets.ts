import { shallowRef } from 'vue'
import { requestJson } from '../api/http'
import { invalidateAvailableGoogleSheets } from './useAvailableGoogleSheets'
import type { GoogleSheetItem } from '../types/system'

export function useGoogleSheets() {
  const sheets = shallowRef<GoogleSheetItem[]>([])
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  async function load() {
    loading.value = true
    errorMessage.value = ''
    try {
      const payload = await requestJson<{ status: string; items: GoogleSheetItem[] }>('/api/google-sheets?include_inactive=1')
      if (payload.status !== 'success') throw new Error('加载 Google Sheet 失败')
      sheets.value = payload.items || []
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '加载 Google Sheet 失败'
    } finally {
      loading.value = false
    }
  }

  async function save(sheet: Partial<GoogleSheetItem>) {
    const url = sheet.id ? `/api/google-sheets/${sheet.id}` : '/api/google-sheets'
    await requestJson(url, { method: sheet.id ? 'PUT' : 'POST', body: JSON.stringify(sheet) })
    invalidateAvailableGoogleSheets()
    await load()
  }

  async function remove(sheetId: number) {
    await requestJson(`/api/google-sheets/${sheetId}`, { method: 'DELETE' })
    invalidateAvailableGoogleSheets()
    await load()
  }

  return { sheets, loading, errorMessage, load, save, remove }
}
