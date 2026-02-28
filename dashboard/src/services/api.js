function resolveApiBase() {
  const raw = (import.meta.env.VITE_API_BASE_URL || '').trim()
  if (!raw) return ''
  if (/^https?:\/\/[^/]+$/i.test(raw)) {
    return raw
  }
  return ''
}

const API_BASE = resolveApiBase()

export function buildApiUrl(path) {
  return `${API_BASE}${path}`
}

async function request(path, options = {}) {
  const url = buildApiUrl(path)
  if (import.meta.env.DEV) {
    // Useful when validating subpath hosting: should stay at /api/*, never /briefs/api/*.
    console.debug('[dashboard api]', url)
  }
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json()
}

export const api = {
  listBriefs: () => request('/api/briefs'),
  getBrief: (date) => request(`/api/briefs/${date}`),
  getMetrics: () => request('/api/metrics'),
  query: (payload) => request('/api/query', { method: 'POST', body: JSON.stringify(payload) }),
}
