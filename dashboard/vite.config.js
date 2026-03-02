import { execSync } from 'node:child_process'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

function normalizeBasePath(value) {
  if (!value || value === '/') return '/'
  const withLeading = value.startsWith('/') ? value : `/${value}`
  return withLeading.endsWith('/') ? withLeading : `${withLeading}/`
}

function parseAllowedHosts(value) {
  return (value || '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const appBase = normalizeBasePath(env.VITE_APP_BASE || '/')
  const allowedHosts = parseAllowedHosts(env.VITE_ALLOWED_HOSTS)
  let buildSha = env.VITE_BUILD_SHA || 'dev'
  let buildTime = env.VITE_BUILD_TIME || new Date().toISOString()
  try {
    if (!env.VITE_BUILD_SHA) {
      buildSha = execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
    }
  } catch (_) {
    // Keep fallback build sha.
  }

  return {
    plugins: [react()],
    base: appBase,
    define: {
      __APP_BUILD_SHA__: JSON.stringify(buildSha),
      __APP_BUILD_TIME__: JSON.stringify(buildTime),
    },
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
