import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/admin/api': 'http://127.0.0.1:5000',
      '/xpl': 'http://127.0.0.1:5000',
    },
  },
})
