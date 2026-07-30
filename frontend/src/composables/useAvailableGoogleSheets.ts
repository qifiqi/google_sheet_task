import { shallowReadonly, shallowRef } from 'vue'
import type { ShallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { GoogleSheetItem } from '../types/system'

const CACHE_TTL_MS = 60_000
const WORKSHEET_CACHE_TTL_MS = 5 * 60_000

interface AvailableSheetsState {
  sheets: ShallowRef<GoogleSheetItem[]>
  options: ShallowRef<GoogleSheetSelectOption[]>
  loading: ShallowRef<boolean>
  loadedAt: number
  pendingRequest: Promise<GoogleSheetItem[]> | null
}

export interface GoogleSheetSelectOption {
  label: string
  value: string
}

export interface GoogleSheetWorksheets {
  title: string
  worksheets: string[]
  options: GoogleSheetSelectOption[]
}

interface WorksheetState {
  data: GoogleSheetWorksheets | null
  loadedAt: number
  pendingRequest: Promise<GoogleSheetWorksheets> | null
}

const states = new Map<string, AvailableSheetsState>()
const worksheetStates = new Map<string, WorksheetState>()

function getState(tableType = '') {
  const key = tableType.trim().toLowerCase()
  let state = states.get(key)
  if (!state) {
    state = {
      sheets: shallowRef<GoogleSheetItem[]>([]),
      options: shallowRef<GoogleSheetSelectOption[]>([]),
      loading: shallowRef(false),
      loadedAt: 0,
      pendingRequest: null,
    }
    states.set(key, state)
  }
  return { key, state }
}

async function loadSheetsByType(tableType = '', force = false) {
  const { key, state } = getState(tableType)
  const isFresh = state.sheets.value.length > 0 && Date.now() - state.loadedAt < CACHE_TTL_MS
  if (!force && isFresh) return state.sheets.value
  if (state.pendingRequest) return state.pendingRequest

  const query = new URLSearchParams({ only_available: '1' })
  if (key) query.set('table_type', key)

  state.loading.value = true
  state.pendingRequest = requestJson<{ status: string; items: GoogleSheetItem[] }>(`/api/google-sheets?${query}`)
    .then((payload) => {
      state.sheets.value = payload.items || []
      state.options.value = state.sheets.value.map((item) => ({
        label: item.name ? `${item.name} (${item.spreadsheet_id})` : item.spreadsheet_id,
        value: item.spreadsheet_id,
      }))
      state.loadedAt = Date.now()
      return state.sheets.value
    })
    .finally(() => {
      state.loading.value = false
      state.pendingRequest = null
    })

  return state.pendingRequest
}

export async function loadAvailableGoogleSheets(force = false) {
  return loadSheetsByType('', force)
}

export function invalidateAvailableGoogleSheets(tableType?: string) {
  if (tableType !== undefined) {
    getState(tableType).state.loadedAt = 0
    return
  }
  states.forEach((state) => { state.loadedAt = 0 })
}

export function useAvailableGoogleSheets(tableType = '') {
  const { state } = getState(tableType)
  return {
    sheets: shallowReadonly(state.sheets),
    options: shallowReadonly(state.options),
    loading: shallowReadonly(state.loading),
    loadSheets: (force = false) => loadSheetsByType(tableType, force),
  }
}

export async function loadGoogleSheetWorksheets(options: {
  spreadsheetId: string
  proxyUrl?: string
  force?: boolean
}) {
  const spreadsheetId = options.spreadsheetId.trim()
  if (!spreadsheetId) return { title: '', worksheets: [], options: [] }

  const proxyUrl = options.proxyUrl?.trim() || ''
  const key = JSON.stringify([spreadsheetId, proxyUrl])
  let state = worksheetStates.get(key)
  if (!state) {
    state = { data: null, loadedAt: 0, pendingRequest: null }
    worksheetStates.set(key, state)
  }

  const isFresh = state.data !== null && Date.now() - state.loadedAt < WORKSHEET_CACHE_TTL_MS
  if (!options.force && isFresh && state.data) return state.data
  if (state.pendingRequest) return state.pendingRequest

  state.pendingRequest = requestJson<{ status: string; title: string; worksheets: string[] }>('/api/google-sheet/worksheets', {
    method: 'POST',
    body: JSON.stringify({ spreadsheet_id: spreadsheetId, proxy_url: proxyUrl || null }),
  })
    .then((payload) => {
      const worksheets = payload.worksheets || []
      const data = {
        title: payload.title || '',
        worksheets,
        options: worksheets.map((worksheet) => ({ label: worksheet, value: worksheet })),
      }
      state.data = data
      state.loadedAt = Date.now()
      return data
    })
    .finally(() => {
      state.pendingRequest = null
    })

  return state.pendingRequest
}
