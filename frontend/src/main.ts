import { createApp } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { ElLoading } from 'element-plus'
import { createPinia } from 'pinia'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import './style.css'
import App from './App.vue'
import router from './router'
import { useAdminPreferencesStore } from './stores/admin-preferences'

const pinia = createPinia()
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
})

useAdminPreferencesStore(pinia).applyTheme()

createApp(App)
  .use(pinia)
  .use(VueQueryPlugin, { queryClient })
  .use(router)
  .use(ElLoading)
  .mount('#app')
