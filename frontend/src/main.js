import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/index.scss'
import App from './App.vue'
import router from './router'
import permissionDirective from './directives/permission'

createApp(App).use(ElementPlus).use(router).use(permissionDirective).mount('#app')
