import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const allowedHosts = [
  'node1.tailb058fe.ts.net',
]

function normalizeBasePath(value) {
  if (!value || value === '/') return '/'
  const withLeading = value.startsWith('/') ? value : `/${value}`
  return withLeading.endsWith('/') ? withLeading : `${withLeading}/`
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const appBase = normalizeBasePath(env.VITE_APP_BASE || '/')

  return {
    plugins: [react()],
    base: appBase,
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
  }
})
