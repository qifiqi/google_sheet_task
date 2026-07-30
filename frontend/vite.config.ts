import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    Components({
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/admin/api': 'http://127.0.0.1:5000',
      '/backtest-training': 'http://127.0.0.1:5000',
      '/backtest-multi-product': 'http://127.0.0.1:5000',
      '/static': 'http://127.0.0.1:5000',
      '/xpl': 'http://127.0.0.1:5000',
    },
  },
})
