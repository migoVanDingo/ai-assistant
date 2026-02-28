import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const allowedHosts = [
  'node1.tailb058fe.ts.net',
]

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
