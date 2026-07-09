import { computed, readonly, shallowRef } from 'vue'
import { clearTokens, getAccessToken, requestEnvelope, requestJson, setTokens } from '../api/http'
import type { ApiEnvelope, CurrentUser, LoginResponse } from '../types/api'

const currentUser = shallowRef<CurrentUser | null>(null)
const loading = shallowRef(false)
const initialized = shallowRef(false)

function applyUser(user: CurrentUser | null) {
  currentUser.value = user
  initialized.value = true
}

async function login(username: string, password: string) {
  loading.value = true
  try {
    const data = await requestEnvelope<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setTokens(data.access_token, data.refresh_token)
    applyUser(data.user)
    return data.user
  } finally {
    loading.value = false
  }
}

async function loadCurrentUser() {
  if (!getAccessToken()) {
    applyUser(null)
    return null
  }

  loading.value = true
  try {
    const user = await requestEnvelope<CurrentUser>('/api/auth/me')
    applyUser(user)
    return user
  } catch (_error) {
    clearTokens()
    applyUser(null)
    return null
  } finally {
    loading.value = false
  }
}

async function logout() {
  try {
    if (getAccessToken()) {
      await requestJson<ApiEnvelope<null>>('/api/auth/logout', { method: 'POST' })
    }
  } finally {
    clearTokens()
    applyUser(null)
  }
}

function hasPermission(code?: string) {
  if (!code) {
    return true
  }
  return Boolean(currentUser.value?.permissions?.includes(code))
}

export function useAuth() {
  const roleText = computed(() => {
    const roles = currentUser.value?.roles || []
    return roles.length ? roles.map((role) => role.name || role.code).filter(Boolean).join(' / ') : '当前账户'
  })

  return {
    currentUser: readonly(currentUser),
    initialized: readonly(initialized),
    loading: readonly(loading),
    isAuthenticated: computed(() => Boolean(currentUser.value)),
    permissions: computed(() => currentUser.value?.permissions || []),
    roleText,
    login,
    loadCurrentUser,
    logout,
    hasPermission,
  }
}
