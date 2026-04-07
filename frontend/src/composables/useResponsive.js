import { computed, ref, onMounted, onUnmounted } from 'vue'
import { breakpoints, getDeviceType, getResponsivePreset } from '@/config/responsive'

export function useResponsive() {
  const width = ref(window.innerWidth)
  const deviceType = ref(getDeviceType(window.innerWidth))
  const preset = ref(getResponsivePreset(window.innerWidth))
  const isMobile = computed(() => deviceType.value === 'mobile')
  const isTablet = computed(() => deviceType.value === 'tablet')
  const isDesktop = computed(() => deviceType.value === 'desktop')

  function update() {
    width.value = window.innerWidth
    deviceType.value = getDeviceType(width.value)
    preset.value = getResponsivePreset(width.value)
  }

  onMounted(() => window.addEventListener('resize', update))
  onUnmounted(() => window.removeEventListener('resize', update))

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
