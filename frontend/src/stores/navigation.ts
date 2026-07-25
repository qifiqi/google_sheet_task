import { computed, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { requestEnvelope } from '../api/http'
import type { NavItem } from '../types/api'

function collectLeaves(items: readonly NavItem[], result: NavItem[] = []) {
  items.forEach((item) => {
    if (item.path) {
      result.push(item)
      return
    }
    collectLeaves(item.children || [], result)
  })
  return result
}

export const useNavigationStore = defineStore('navigation', () => {
  const navItems = shallowRef<NavItem[]>([])
  const loading = shallowRef(false)
  const navLeaves = computed(() => collectLeaves(navItems.value))

  async function loadNavigation() {
    loading.value = true
    try {
      navItems.value = await requestEnvelope<NavItem[]>('/api/meta/nav')
      return navItems.value
    } finally {
      loading.value = false
    }
  }

  return { navItems, navLeaves, loading, loadNavigation }
})
