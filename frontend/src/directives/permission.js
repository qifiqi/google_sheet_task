import { useAuth } from '@/composables/useAuth'

export const vPermission = {
  mounted(el, binding) {
    const { hasPermission } = useAuth()
    if (!hasPermission(binding.value)) {
      el.parentNode?.removeChild(el)
    }
  },
}

export default {
  install(app) {
    app.directive('permission', vPermission)
  },
}
