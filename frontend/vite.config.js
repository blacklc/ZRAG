/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/zrag/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/zrag/v1': { target: 'http://localhost:5965', rewrite: (p) => p.replace(/^\/zrag/, '') },
      '/v1': 'http://localhost:5965',
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
  },
})
