import { ref } from 'vue'
import { getNav } from '@/api/meta'

const navItems = ref([])
let navPromise = null

const LEGACY_PATH_MAP = {
  '/google-sheet/?version=c3': '/task/list?version=c3',
  '/google-sheet/?version=c4': '/task/list?version=c4',
  '/google-sheet/?version=c5': '/task/list?version=c5',
  '/backtest-training/list': '/backtest/list',
  '/backtest-multi-product/list': '/backtest-multi/list',
}

function normalizePaths(items) {
  return items.map((item) => {
    const normalized = { ...item }
    if (normalized.path && LEGACY_PATH_MAP[normalized.path]) {
      normalized.path = LEGACY_PATH_MAP[normalized.path]
    }
    if (Array.isArray(normalized.children)) {
      normalized.children = normalizePaths(normalized.children)
    }
    return normalized
  })
}

export function useNavigation() {
  async function ensureNavLoaded() {
    if (navItems.value.length) {
      return navItems.value
    }

    if (!navPromise) {
      navPromise = getNav()
        .then((res) => {
          const raw = Array.isArray(res.data) ? res.data : []
          navItems.value = normalizePaths(raw)
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
