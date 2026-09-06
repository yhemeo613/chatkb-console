import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式：npm run dev（5173 端口，/api 代理到 8000 后端）
// 生产模式：npm run build 后由 FastAPI 直接托管 dist/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
