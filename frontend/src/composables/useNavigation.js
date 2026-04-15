import { ref } from 'vue'
import { getNav } from '@/api/meta'

const navItems = ref([])
let navPromise = null

export function useNavigation() {
  async function ensureNavLoaded() {
    if (navItems.value.length) {
      return navItems.value
    }

    if (!navPromise) {
      navPromise = getNav()
        .then((res) => {
          navItems.value = Array.isArray(res.data) ? res.data : []
          return navItems.value
        })
        .catch(() => {
          navItems.value = []
          return navItems.value
        })
        .finally(() => {
          navPromise = null
        })
    }

    return navPromise
  }

  return {
    navItems,
    ensureNavLoaded,
  }
}
