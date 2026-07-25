import { useSessionStorage, useStorage } from '@vueuse/core'
import { defineStore } from 'pinia'

export type AdminTheme = 'light' | 'dark'

export const useAdminPreferencesStore = defineStore('admin-preferences', () => {
  const theme = useStorage<AdminTheme>('admin_theme', 'light')
  const sidebarCollapsed = useStorage('admin_sidebar_collapsed', false)
  const closedTabKeys = useSessionStorage<string[]>('admin_closed_tabs', [])

  function applyTheme(nextTheme = theme.value) {
    theme.value = nextTheme
    document.documentElement.dataset.theme = nextTheme
  }

  function toggleTheme() {
    applyTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  function closeTab(key: string) {
    if (!closedTabKeys.value.includes(key)) {
      closedTabKeys.value = [...closedTabKeys.value, key]
    }
  }

  function reopenTab(key: string) {
    closedTabKeys.value = closedTabKeys.value.filter((item) => item !== key)
  }

  return {
    theme,
    sidebarCollapsed,
    closedTabKeys,
    applyTheme,
    toggleTheme,
    closeTab,
    reopenTab,
  }
})
