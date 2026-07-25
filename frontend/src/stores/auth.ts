import { computed, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { clearTokens, getAccessToken, requestEnvelope, requestJson, setTokens } from '../api/http'
import type { ApiEnvelope, CurrentUser, LoginResponse } from '../types/api'

export const useAuthStore = defineStore('auth', () => {
  const currentUser = shallowRef<CurrentUser | null>(null)
  const loading = shallowRef(false)
  const initialized = shallowRef(false)
  const isAuthenticated = computed(() => Boolean(currentUser.value))
  const permissions = computed(() => currentUser.value?.permissions || [])
  const roleText = computed(() => {
    const roles = currentUser.value?.roles || []
    return roles.length ? roles.map((role) => role.name || role.code).filter(Boolean).join(' / ') : '当前账户'
  })

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
    } catch {
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
    return !code || permissions.value.includes(code)
  }

  return { currentUser, loading, initialized, isAuthenticated, permissions, roleText, login, loadCurrentUser, logout, hasPermission }
})
