import { ref, computed } from 'vue'
import { login as loginApi, logout as logoutApi, refreshToken as refreshApi, getMe } from '@/api/auth'

const TOKEN_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'
// 与后端 ACCESS_TOKEN_COOKIE(gsc_access_token) 同名：页面导航请求无法携带
// Authorization 头，服务端页面鉴权（page_login_required）据此回退读取。
// 名字不按端口隔离，通用名会被本机其他服务的同名（HttpOnly）cookie 顶死。
const ACCESS_COOKIE_KEY = 'gsc_access_token'

const user = ref(null)
const permissions = ref([])
let fetchUserPromise = null

// access_token 同步写 cookie（path=/ + SameSite=Lax，https 下加 Secure）。
// 注意：api/index.js 401 刷新路径内联了同一实现（api 层禁止反向 import
// composables），两处属性须同步修改。
function writeAccessTokenCookie(accessToken) {
  const securePart = window.location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `${ACCESS_COOKIE_KEY}=${encodeURIComponent(accessToken)}; path=/; SameSite=Lax${securePart}`
}

function clearAccessTokenCookie() {
  // 置空并立即过期，清除页面鉴权用的访问令牌 cookie。
  document.cookie = `${ACCESS_COOKIE_KEY}=; path=/; SameSite=Lax; Max-Age=0`
}

// 统一 setTokens 管线（对齐静态版 template-auth.js）：refresh_token 缺省时
// 保留旧值，兼容旧版仅返回 access_token 的情况。
function setTokens(accessToken, refreshToken) {
  if (accessToken) {
    localStorage.setItem(TOKEN_KEY, accessToken)
    writeAccessTokenCookie(accessToken)
  }
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken)
  }
}

function clearAuthState() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  clearAccessTokenCookie()
  user.value = null
  permissions.value = []
  fetchUserPromise = null
}

// 登录态数据落盘（SSO 换票/账密登录共用的响应结构 {access_token, refresh_token, user}）。
function applyAuthData(data) {
  setTokens(data.access_token, data.refresh_token)
  user.value = data.user || null
  permissions.value = (data.user && data.user.permissions) || []
}

export function useAuth() {
  const isLoggedIn = computed(() => !!localStorage.getItem(TOKEN_KEY))

  async function login(username, password) {
    const res = await loginApi({ username, password })
    applyAuthData(res)
    return res
  }

  // 对齐静态版：先通知后端注销（失败照常清本地），finally 里清本地态。
  async function logout() {
    try {
      if (getToken()) {
        await logoutApi()
      }
    } catch {
      // 后端注销失败不阻断本地清理
    } finally {
      clearAuthState()
    }
  }

  async function refresh() {
    const rt = localStorage.getItem(REFRESH_KEY)
    if (!rt) throw new Error('No refresh token')
    const res = await refreshApi({ refresh_token: rt })
    // 后端会轮换 refresh_token（滑动续期），一并持久化；未返回则保留旧值。
    setTokens(res.access_token, res.refresh_token || rt)
    user.value = res.user
    permissions.value = res.user.permissions || []
    return res
  }

  async function fetchUser() {
    if (!localStorage.getItem(TOKEN_KEY)) return
    if (fetchUserPromise) return fetchUserPromise

    fetchUserPromise = (async () => {
      try {
        const res = await getMe()
        user.value = res
        permissions.value = res.permissions || []
        return res
      } catch {
        // 对齐静态版：登录态恢复失败仅清本地（此时再调后端注销无意义）。
        clearAuthState()
        return null
      } finally {
        fetchUserPromise = null
      }
    })()

    return fetchUserPromise
  }

  function hasPermission(code) {
    // 接口权限保留在用户数据中，但不再限制页面内操作。
    if (!String(code || '').startsWith('page:')) return true
    return permissions.value.includes(code)
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY)
  }

  return { user, permissions, isLoggedIn, login, logout, refresh, fetchUser, hasPermission, getToken, applyAuthData }
}
