import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ['vue', 'vue-router', 'pinia'],
      dts: true // 生成类型声明文件
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: true // 生成类型声明文件
    })
  ],
  server: {
    port: 8080,
    host: '0.0.0.0', // 允许外部访问
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../static/dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 手动分包，优化加载性能
        manualChunks: {
          'element-plus': ['element-plus'],
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'utils': ['axios', 'dayjs']
        },
        // 资源文件命名
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split('.')
          const extType = info[info.length - 1]
          if (/\.(mp4|webm|ogg|mp3|wav|flac|aac)(\?.*)?$/i.test(assetInfo.name)) {
            return `assets/media/[name]-[hash].${extType}`
          }
          if (/\.(png|jpe?g|gif|svg)(\?.*)?$/.test(assetInfo.name)) {
            return `assets/images/[name]-[hash].${extType}`
          }
          if (/\.(woff2?|eot|ttf|otf)(\?.*)?$/i.test(assetInfo.name)) {
            return `assets/fonts/[name]-[hash].${extType}`
          }
          return `assets/[ext]/[name]-[hash].${extType}`
        }
      }
    },
    // 启用 gzip 压缩
    reportCompressedSize: true,
    // 调整 chunk 大小警告限制
    chunkSizeWarningLimit: 1000
  },
  // 优化依赖预构建
  optimizeDeps: {
    include: [
      'vue', 
      'vue-router', 
      'pinia', 
      'element-plus/es',
      'axios', 
      'dayjs'
    ]
  },
  // CSS 预处理器配置
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler' // 使用现代编译器API，解决警告
      }
    }
  }
})
