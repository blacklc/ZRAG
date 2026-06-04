/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/v1': 'http://localhost:5965' } },
  test: {
    environment: 'happy-dom',
    globals: true,
  },
})
