import { defineConfig } from 'vite'
import path from 'path'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/admin/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/backtest-training/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/xpl/analyze': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/xpl/export': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/xpl/v1/analyze': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
