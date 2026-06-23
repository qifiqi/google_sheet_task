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

function applyTheme(nextTheme) {
  theme.value = nextTheme

  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = nextTheme
    document.documentElement.classList.toggle('dark', nextTheme === 'dark')
  }

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_KEY, nextTheme)
  }
}

if (typeof window !== 'undefined') {
  applyTheme(resolveInitialTheme())
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
