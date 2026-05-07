import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 将 /api 请求代理到后端服务器
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // 将 /output 请求代理到后端（图表、报告等静态资源）
      '/output': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 生产构建输出目录
    outDir: 'dist',
    // 资源引用基础路径（支持部署到子路径）
    base: '/',
  },
  // 环境变量前缀
  envPrefix: 'VITE_',
})
