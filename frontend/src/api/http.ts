import type { ApiEnvelope, RefreshResponse } from '../types/api'

const TOKEN_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

let refreshPromise: Promise<string> | null = null

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY) || ''
}

export function setTokens(accessToken?: string, refreshToken?: string) {
  if (accessToken) {
    localStorage.setItem(TOKEN_KEY, accessToken)
  }
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken)
  }
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

async function parseJson<T>(response: Response): Promise<T | null> {
  const text = await response.text()
  if (!text) {
    return null
  }
  return JSON.parse(text) as T
}

async function refreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: getRefreshToken() }),
  })
    .then(async (response) => {
      const payload = await parseJson<ApiEnvelope<RefreshResponse>>(response)
      if (!response.ok || !payload || payload.code !== 0) {
        throw new Error(payload?.message || '刷新登录状态失败')
      }
      setTokens(payload.data.access_token)
      return payload.data.access_token
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

export async function requestJson<T>(url: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getAccessToken()

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(url, { ...options, headers })
  if (response.status === 401 && retry && getRefreshToken()) {
    const newToken = await refreshAccessToken()
    const retryHeaders = new Headers(headers)
    retryHeaders.set('Authorization', `Bearer ${newToken}`)
    return requestJson<T>(url, { ...options, headers: retryHeaders }, false)
  }

  const payload = await parseJson<T>(response)
  if (!response.ok) {
    const message = typeof payload === 'object' && payload && 'message' in payload
      ? String((payload as { message?: string }).message)
      : `请求失败: ${response.status}`
    throw new Error(message)
  }
  if (!payload) {
    throw new Error('接口未返回数据')
  }

  return payload
}

export async function requestEnvelope<T>(url: string, options: RequestInit = {}) {
  const payload = await requestJson<ApiEnvelope<T>>(url, options)
  if (payload.code !== 0) {
    throw new Error(payload.message || '请求失败')
  }
  return payload.data
}
