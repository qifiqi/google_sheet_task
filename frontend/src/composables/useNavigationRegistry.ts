import { shallowRef } from 'vue'
import { requestJson } from '../api/http'
import type { NavigationRegistryItem } from '../types/system'

export function useNavigationRegistry() {
  const items = shallowRef<NavigationRegistryItem[]>([])
  const loading = shallowRef(false)
  const errorMessage = shallowRef('')

  async function load() {
    loading.value = true; errorMessage.value = ''
    try {
      const payload = await requestJson<{ status: string; items: NavigationRegistryItem[] }>('/api/navigation-menu-items')
      if (payload.status !== 'success') throw new Error('加载路由表失败')
      items.value = payload.items || []
    } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载路由表失败' } finally { loading.value = false }
  }

  async function save(item: Partial<NavigationRegistryItem>) {
    const target = item.id ? `/api/navigation-menu-items/${item.id}` : '/api/navigation-menu-items'
    await requestJson(target, { method: item.id ? 'PUT' : 'POST', body: JSON.stringify(item) })
    await load()
  }

  async function remove(itemId: number) {
    await requestJson(`/api/navigation-menu-items/${itemId}`, { method: 'DELETE' })
    await load()
  }

  return { items, loading, errorMessage, load, save, remove }
}
