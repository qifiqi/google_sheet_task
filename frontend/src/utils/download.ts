import { getAccessToken } from '../api/http'

export async function downloadFile(url: string, fallbackFilename: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers)
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(url, { ...options, headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.message || `下载失败: ${response.status}`)
  }

  const blob = await response.blob()
  const filename = filenameFromDisposition(response.headers.get('Content-Disposition')) || fallbackFilename
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

function filenameFromDisposition(contentDisposition: string | null) {
  if (!contentDisposition) return ''
  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch) return decodeURIComponent(encodedMatch[1])
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] || ''
}

export function downloadTextFile(content: string, filename: string, type = 'text/plain;charset=utf-8') {
  const objectUrl = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}
