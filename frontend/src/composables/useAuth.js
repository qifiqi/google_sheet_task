import { ref, computed } from 'vue'
import { getMe } from '@/api/auth'

// 鉴权模式（单 Token 子服务模式，2026-09 启用）:
// - Token 由主 Web 登录后颁发，本服务不提供账号密码登录;
//   login(token) 仅做校验并存储（支持主 Web 跳转携带 ?token= 的场景）。
// - 无 refresh_token 换发流程; 401 由 http 拦截器统一登出。
// 旧账号密码登录 / 刷新令牌实现注释保留在文件底部。

const TOKEN_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

const user = ref(null)
const permissions = ref([])
let fetchUserPromise = null

export function useAuth() {
  const isLoggedIn = computed(() => !!localStorage.getItem(TOKEN_KEY))

  async function login(token) {
    // 单 Token 模式: 校验主 Web 颁发的 Token 并存储。
    const trimmed = String(token || '').trim()
    if (!trimmed) throw new Error('请输入 Token')
    localStorage.setItem(TOKEN_KEY, trimmed)
    try {
      await fetchUser(true)
    } catch (err) {
      logout()
      throw err
    }
    return user.value
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    user.value = null
    permissions.value = []
    fetchUserPromise = null
  }

  async function fetchUser(force = false) {
    if (!localStorage.getItem(TOKEN_KEY)) return
    if (!force && fetchUserPromise) return fetchUserPromise

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
    // 接口权限保留在用户数据中，但不再限制页面内操作；
    // 页面可见性由 GetUserRoleList 路由表控制（见 /api/meta/nav）。
    if (!String(code || '').startsWith('page:')) return true
    return permissions.value.includes(code)
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY)
  }

  return { user, permissions, isLoggedIn, login, logout, fetchUser, hasPermission, getToken }
}

// ---------- 旧账号密码登录 / 刷新令牌实现（注释保留，便于恢复本地登录） ----------
// import { login as loginApi, refreshToken as refreshApi } from '@/api/auth'
//
//   async function login(username, password) {
//     const res = await loginApi({ username, password })
//     localStorage.setItem(TOKEN_KEY, res.data.access_token)
//     localStorage.setItem(REFRESH_KEY, res.data.refresh_token)
//     user.value = res.data.user
//     permissions.value = res.data.user.permissions || []
//     return res
//   }
//
//   async function refresh() {
//     const rt = localStorage.getItem(REFRESH_KEY)
//     if (!rt) throw new Error('No refresh token')
//     const res = await refreshApi({ refresh_token: rt })
//     localStorage.setItem(TOKEN_KEY, res.data.access_token)
//     user.value = res.data.user
//     permissions.value = res.data.user.permissions || []
//     return res
//   }
