import { ref, computed } from 'vue'
import { login as loginApi, refreshToken as refreshApi, getMe } from '@/api/auth'

const TOKEN_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

const user = ref(null)
const permissions = ref([])
let fetchUserPromise = null

export function useAuth() {
  const isLoggedIn = computed(() => !!localStorage.getItem(TOKEN_KEY))

  async function login(username, password) {
    const res = await loginApi({ username, password })
    localStorage.setItem(TOKEN_KEY, res.data.access_token)
    localStorage.setItem(REFRESH_KEY, res.data.refresh_token)
    user.value = res.data.user
    permissions.value = res.data.user.permissions || []
    return res
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    user.value = null
    permissions.value = []
    fetchUserPromise = null
  }

  async function refresh() {
    const rt = localStorage.getItem(REFRESH_KEY)
    if (!rt) throw new Error('No refresh token')
    const res = await refreshApi({ refresh_token: rt })
    localStorage.setItem(TOKEN_KEY, res.data.access_token)
    user.value = res.data.user
    permissions.value = res.data.user.permissions || []
    return res
  }

  async function fetchUser() {
    if (!localStorage.getItem(TOKEN_KEY)) return
    if (fetchUserPromise) return fetchUserPromise

    fetchUserPromise = (async () => {
      try {
        const res = await getMe()
        user.value = res.data
        permissions.value = res.data.permissions || []
        return res
      } catch {
        logout()
        return null
      } finally {
        fetchUserPromise = null
      }
    })()

    return fetchUserPromise
  }

  function hasPermission(code) {
    return permissions.value.includes(code)
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY)
  }

  return { user, permissions, isLoggedIn, login, logout, refresh, fetchUser, hasPermission, getToken }
}
