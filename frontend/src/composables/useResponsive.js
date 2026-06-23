import { computed, ref } from 'vue'
import { breakpoints, getDeviceType, getResponsivePreset } from '@/config/responsive'

const width = ref(typeof window === 'undefined' ? breakpoints.xl : window.innerWidth)
const deviceType = ref(getDeviceType(width.value))
const preset = ref(getResponsivePreset(width.value))

let listening = false
let rafId = 0

function syncResponsiveState(nextWidth = window.innerWidth) {
  width.value = nextWidth
  deviceType.value = getDeviceType(nextWidth)
  preset.value = getResponsivePreset(nextWidth)
}

function handleResize() {
  if (rafId) {
    cancelAnimationFrame(rafId)
  }
  rafId = requestAnimationFrame(() => {
    syncResponsiveState(window.innerWidth)
    rafId = 0
  })
}

function ensureResponsiveListener() {
  if (listening || typeof window === 'undefined') {
    return
  }
  listening = true
  syncResponsiveState(window.innerWidth)
  window.addEventListener('resize', handleResize, { passive: true })
}

export function useResponsive() {
  ensureResponsiveListener()

  const isMobile = computed(() => deviceType.value === 'mobile')
  const isTablet = computed(() => deviceType.value === 'tablet')
  const isDesktop = computed(() => deviceType.value === 'desktop')

  return {
    width,
    breakpoints,
    deviceType,
    preset,
    isMobile,
    isTablet,
    isDesktop,
    componentSize: computed(() => preset.value.componentSize),
    dialogWidth: computed(() => preset.value.dialogWidth),
    drawerSize: computed(() => preset.value.drawerSize),
    formLabelPosition: computed(() => preset.value.formLabelPosition),
    formLabelWidth: computed(() => preset.value.formLabelWidth),
    pagePadding: computed(() => preset.value.pagePadding),
    headerHeight: computed(() => preset.value.headerHeight),
    sidebarWidth: computed(() => preset.value.sidebarWidth),
    tablePageSize: computed(() => preset.value.tablePageSize),
  }
}
