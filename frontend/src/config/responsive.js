export const breakpoints = {
  xs: 0,
  sm: 576,
  md: 768,
  lg: 992,
  xl: 1200,
  xxl: 1600,
}

export function getDeviceType(width = window.innerWidth) {
  if (width < breakpoints.md) return 'mobile'
  if (width < breakpoints.xl) return 'tablet'
  return 'desktop'
}

export function getResponsivePreset(width = window.innerWidth) {
  const deviceType = getDeviceType(width)

  if (deviceType === 'mobile') {
    return {
      deviceType,
      componentSize: 'small',
      dialogWidth: '95%',
      drawerSize: '100%',
      formLabelPosition: 'top',
      formLabelWidth: 'auto',
      pagePadding: 12,
      headerHeight: 56,
      sidebarWidth: 240,
      tablePageSize: 10,
    }
  }

  if (deviceType === 'tablet') {
    return {
      deviceType,
      componentSize: 'default',
      dialogWidth: '720px',
      drawerSize: '640px',
      formLabelPosition: 'right',
      formLabelWidth: '96px',
      pagePadding: 20,
      headerHeight: 56,
      sidebarWidth: 220,
      tablePageSize: 20,
    }
  }

  return {
    deviceType,
    componentSize: 'default',
    dialogWidth: '840px',
    drawerSize: '640px',
    formLabelPosition: 'right',
    formLabelWidth: '100px',
    pagePadding: 24,
    headerHeight: 60,
    sidebarWidth: 240,
    tablePageSize: 20,
  }
}
