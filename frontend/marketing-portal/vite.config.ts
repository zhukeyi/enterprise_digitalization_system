import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/marketing/',
  server: {
    proxy: {
      '/fde-api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
