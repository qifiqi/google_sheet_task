import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/admin/api': 'http://127.0.0.1:5000',
      // C4/C5/C7 detail and creation pages are still served by Flask while their
      // Vue replacements are completed. Without this proxy, Vite's SPA fallback
      // resolves those legacy return links to the dashboard.
      '/google-sheet': 'http://127.0.0.1:5000',
      '/backtest-training': 'http://127.0.0.1:5000',
      '/backtest-multi-product': 'http://127.0.0.1:5000',
      '/static': 'http://127.0.0.1:5000',
      '/xpl': 'http://127.0.0.1:5000',
    },
  },
})
