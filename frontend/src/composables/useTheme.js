import { computed, ref } from 'vue'

const THEME_KEY = 'app_theme'
const theme = ref('light')

function resolveInitialTheme() {
  if (typeof window === 'undefined') {
    return 'light'
  }

  const savedTheme = window.localStorage.getItem(THEME_KEY)
  if (savedTheme === 'light' || savedTheme === 'dark') {
    return savedTheme
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(nextTheme, { persist = true } = {}) {
  theme.value = nextTheme

  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = nextTheme
    document.documentElement.classList.toggle('dark', nextTheme === 'dark')
  }

  if (persist && typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_KEY, nextTheme)
  }
}

if (typeof window !== 'undefined') {
  applyTheme(resolveInitialTheme(), { persist: false })

  // 用户未显式选择主题时跟随系统明暗变化。
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  media.addEventListener?.('change', (event) => {
    if (!window.localStorage.getItem(THEME_KEY)) {
      applyTheme(event.matches ? 'dark' : 'light', { persist: false })
    }
  })
}

export function useTheme() {
  const isDark = computed(() => theme.value === 'dark')
  const switchValue = computed({
    get: () => isDark.value,
    set: (enabled) => applyTheme(enabled ? 'dark' : 'light'),
  })

  function toggleTheme() {
    applyTheme(isDark.value ? 'light' : 'dark')
  }

  return {
    theme,
    isDark,
    switchValue,
    toggleTheme,
    applyTheme,
  }
}
