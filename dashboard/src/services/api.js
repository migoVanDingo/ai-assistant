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
    let detail = ''
    if (text) {
      try {
        const payload = JSON.parse(text)
        if (payload && typeof payload === 'object' && payload.detail) {
          detail = String(payload.detail)
        }
      } catch {
        // Fall through to raw response body.
      }
    }
    throw new Error(detail || text || `Request failed: ${response.status}`)
  }
  return response.json()
}

function toQuery(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  return search.toString() ? `?${search.toString()}` : ''
}

export const api = {
  listBriefs: () => request('/api/briefs'),
  getBrief: (date) => request(`/api/briefs/${date}`),
  getMetrics: () => request('/api/metrics'),
  query: (payload) => request('/api/query', { method: 'POST', body: JSON.stringify(payload) }),
  listQueries: (params = {}) => {
    const suffix = toQuery({ days: params.days, limit: params.limit })
    return request(`/api/queries${suffix}`)
  },
  getQuery: (id) => request(`/api/queries/${id}`),
  listStorySources: () => request('/api/stories/sources'),
  listStoryClusters: () => request('/api/stories/clusters'),
  listStoryTags: () => request('/api/stories/tags'),
  listStoryWatchHits: () => request('/api/stories/watch-hits'),
  listStorySections: (params = {}) => {
    const suffix = toQuery({ section_limit: params.section_limit })
    return request(`/api/stories/sections${suffix}`)
  },
  setStoryFeedback: (payload) => request('/api/stories/feedback', { method: 'POST', body: JSON.stringify(payload) }),
  resolveStoryLinks: (payload) => request('/api/stories/resolve-links', { method: 'POST', body: JSON.stringify(payload) }),
  getNightlyJobStatus: () => request('/api/jobs/nightly'),
  runNightlyJob: (payload = {}) => request('/api/jobs/nightly', { method: 'POST', body: JSON.stringify(payload) }),
  importArxivUrl: (payload) => request('/api/arxiv/import', { method: 'POST', body: JSON.stringify(payload) }),
  listFavoriteFolders: () => request('/api/favorites/folders'),
  createFavoriteFolder: (payload) => request('/api/favorites/folders', { method: 'POST', body: JSON.stringify(payload) }),
  addFavoriteItem: (payload) => request('/api/favorites/items', { method: 'POST', body: JSON.stringify(payload) }),
  listFavoriteItems: (params = {}) => {
    const suffix = toQuery({ folder_id: params.folder_id })
    return request(`/api/favorites/items${suffix}`)
  },
  removeFavoriteItem: (params = {}) => request(`/api/favorites/items${toQuery(params)}`, { method: 'DELETE' }),
  queryStories: (payload) => request('/api/stories', { method: 'POST', body: JSON.stringify(payload) }),
}
