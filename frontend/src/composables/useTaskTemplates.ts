import { readonly, shallowRef } from 'vue'
import type { ShallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { TaskTemplate } from '../types/api'

const CACHE_TTL_MS = 60_000

interface TaskTemplateState {
  templates: ShallowRef<TaskTemplate[]>
  loading: ShallowRef<boolean>
  loadedAt: number
  pendingRequest: Promise<TaskTemplate[]> | null
}

const states = new Map<string, TaskTemplateState>()

function getState(taskType: string) {
  const key = taskType.trim().toLowerCase()
  let state = states.get(key)
  if (!state) {
    state = {
      templates: shallowRef<TaskTemplate[]>([]),
      loading: shallowRef(false),
      loadedAt: 0,
      pendingRequest: null,
    }
    states.set(key, state)
  }
  return { key, state }
}

async function loadTemplatesByType(taskType: string, force = false) {
  const { key, state } = getState(taskType)
  const isFresh = state.loadedAt > 0 && Date.now() - state.loadedAt < CACHE_TTL_MS
  if (!force && isFresh) return state.templates.value
  if (state.pendingRequest) return state.pendingRequest

  const query = new URLSearchParams({ task_type: key })
  state.loading.value = true
  state.pendingRequest = requestJson<{ status: string; templates: TaskTemplate[] }>(`/api/templates?${query}`)
    .then((payload) => {
      state.templates.value = payload.templates || []
      state.loadedAt = Date.now()
      return state.templates.value
    })
    .finally(() => {
      state.loading.value = false
      state.pendingRequest = null
    })

  return state.pendingRequest
}

export function useTaskTemplates(taskType: string) {
  const { state } = getState(taskType)
  return {
    templates: readonly(state.templates),
    loading: readonly(state.loading),
    loadTemplates: (force = false) => loadTemplatesByType(taskType, force),
  }
}
