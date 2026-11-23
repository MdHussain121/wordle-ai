import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/profile': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/recommend': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/compare': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/dictionary': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
