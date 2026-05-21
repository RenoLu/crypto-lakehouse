import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://localhost:8000',
      '/assets': 'http://localhost:8000',
      '/market': 'http://localhost:8000',
      '/analytics': 'http://localhost:8000',
      '/portfolio': 'http://localhost:8000',
      '/quality': 'http://localhost:8000',
      '/assistant': 'http://localhost:8000',
    },
  },
})
