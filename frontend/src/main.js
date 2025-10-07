import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

// 自定义样式
import './styles/index.scss'

const app = createApp(App)

// 使用 Pinia 状态管理
app.use(createPinia())

// 使用 Vue Router
app.use(router)

// 挂载应用
app.mount('#app')
