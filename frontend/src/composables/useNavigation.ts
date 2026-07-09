import { computed, readonly, shallowRef } from 'vue'
import { requestEnvelope } from '../api/http'
import type { NavItem } from '../types/api'

const navItems = shallowRef<NavItem[]>([])
const loading = shallowRef(false)

function collectLeaves(items: NavItem[], result: NavItem[] = []) {
  items.forEach((item) => {
    if (item.path) {
      result.push(item)
      return
    }
    collectLeaves(item.children || [], result)
  })
  return result
}

async function loadNavigation() {
  loading.value = true
  try {
    navItems.value = await requestEnvelope<NavItem[]>('/api/meta/nav')
    return navItems.value
  } finally {
    loading.value = false
  }
}

export function useNavigation() {
  return {
    navItems: readonly(navItems),
    navLeaves: computed(() => collectLeaves(navItems.value)),
    loading: readonly(loading),
    loadNavigation,
  }
}
