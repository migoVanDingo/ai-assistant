import {
  CircularProgress,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'

const LIMIT_OPTIONS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

function buildHeading(filters, clusters) {
  if (filters.source_name) return `Source: ${filters.source_name}`
  if (filters.tags.length) return `Tags: ${filters.tags.join(', ')}`
  if (filters.watch_hits.length) return `Watch hits: ${filters.watch_hits.join(', ')}`
  if (filters.cluster_id) {
    const cluster = clusters.find((item) => item.id === filters.cluster_id)
    return `Cluster: ${cluster?.label || filters.cluster_id}`
  }
  return 'All stories'
}

export default function StoriesPage() {
  const [loadingOptions, setLoadingOptions] = useState(true)
  const [loadingResults, setLoadingResults] = useState(true)
  const [error, setError] = useState('')
  const [sources, setSources] = useState([])
  const [clusters, setClusters] = useState([])
  const [tags, setTags] = useState([])
  const [watchHits, setWatchHits] = useState([])
  const [results, setResults] = useState([])
  const [filters, setFilters] = useState({
    source_name: '',
    from_date: '',
    to_date: '',
    limit: 20,
    cluster_id: '',
    tags: [],
    watch_hits: [],
    order: 'desc',
  })

  useEffect(() => {
    async function loadOptions() {
      try {
        setLoadingOptions(true)
        setError('')
        const [sourceList, clusterList, tagList, watchHitList] = await Promise.all([
          api.listStorySources(),
          api.listStoryClusters(),
          api.listStoryTags(),
          api.listStoryWatchHits(),
        ])
        setSources(sourceList)
        setClusters(clusterList)
        setTags(tagList)
        setWatchHits(watchHitList)
      } catch (err) {
        setError(err.message || 'Failed to load story filters.')
      } finally {
        setLoadingOptions(false)
      }
    }
    loadOptions()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        setLoadingResults(true)
        setError('')
        const payload = await api.queryStories(filters)
        setResults(payload.items || [])
      } catch (err) {
        setError(err.message || 'Failed to load stories.')
      } finally {
        setLoadingResults(false)
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [filters])

  const heading = useMemo(() => buildHeading(filters, clusters), [clusters, filters])
  const normalizeMultiValue = (value) => (Array.isArray(value) ? value : String(value).split(',').filter(Boolean))

  return (
    <Stack spacing={3}>
      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={1}>
          <Typography variant="h5">Stories browser</Typography>
          <Typography color="text.secondary">
            Deterministic browsing over archived items, with source, cluster, tag, and watch-hit filters.
          </Typography>
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 4, overflow: 'hidden' }}>
        <Stack spacing={2}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Sources</Typography>
          {loadingOptions ? <Typography color="text.secondary">Loading sources...</Typography> : null}
          <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 0.5 }}>
            {sources.map((source) => (
              <ToggleButton
                key={source}
                value={source}
                selected={filters.source_name === source}
                onChange={() => setFilters((current) => ({ ...current, source_name: current.source_name === source ? '' : source }))}
                sx={{ whiteSpace: 'nowrap', borderRadius: 999 }}
              >
                {source}
              </ToggleButton>
            ))}
          </Stack>
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Filters</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              fullWidth
              label="From date"
              type="date"
              value={filters.from_date}
              onChange={(event) => setFilters((current) => ({ ...current, from_date: event.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              fullWidth
              label="To date"
              type="date"
              value={filters.to_date}
              onChange={(event) => setFilters((current) => ({ ...current, to_date: event.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
            <FormControl fullWidth>
              <InputLabel>Limit</InputLabel>
              <Select
                value={filters.limit}
                label="Limit"
                onChange={(event) => setFilters((current) => ({ ...current, limit: Number(event.target.value) }))}
              >
                {LIMIT_OPTIONS.map((value) => (
                  <MenuItem key={value} value={value}>{value}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <FormControl fullWidth>
              <InputLabel>Cluster</InputLabel>
              <Select
                value={filters.cluster_id}
                label="Cluster"
                onChange={(event) => setFilters((current) => ({ ...current, cluster_id: event.target.value }))}
              >
                <MenuItem value="">All clusters</MenuItem>
                {clusters.map((cluster) => (
                  <MenuItem key={cluster.id} value={cluster.id}>
                    {cluster.label || cluster.id}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel>Tags</InputLabel>
              <Select
                multiple
                value={filters.tags}
                label="Tags"
                renderValue={(selected) => selected.join(', ')}
                onChange={(event) => setFilters((current) => ({ ...current, tags: normalizeMultiValue(event.target.value) }))}
              >
                {tags.map((tag) => (
                  <MenuItem key={tag.tag} value={tag.tag}>
                    <ListItemText primary={tag.tag} secondary={`${tag.count} items`} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel>Watch hits</InputLabel>
              <Select
                multiple
                value={filters.watch_hits}
                label="Watch hits"
                renderValue={(selected) => selected.join(', ')}
                onChange={(event) => setFilters((current) => ({ ...current, watch_hits: normalizeMultiValue(event.target.value) }))}
              >
                {watchHits.map((watchHit) => (
                  <MenuItem key={watchHit.watch_hit} value={watchHit.watch_hit}>
                    <ListItemText primary={watchHit.watch_hit} secondary={`${watchHit.count} items`} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
            <Typography variant="body2" color="text.secondary">Sort by published date</Typography>
            <ToggleButtonGroup
              exclusive
              value={filters.order}
              onChange={(_, value) => value && setFilters((current) => ({ ...current, order: value }))}
              size="small"
            >
              <ToggleButton value="desc">Newest first</ToggleButton>
              <ToggleButton value="asc">Oldest first</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <div>
            <Typography variant="overline" color="text.secondary">Search focus</Typography>
            <Typography variant="h6">{heading}</Typography>
          </div>
          {error ? <Typography color="error">{error}</Typography> : null}
          {loadingResults ? (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={20} />
              <Typography color="text.secondary">Loading stories...</Typography>
            </Stack>
          ) : null}
          {!loadingResults && results.length === 0 ? (
            <Typography color="text.secondary">No stories matched these filters.</Typography>
          ) : null}
          {!loadingResults && results.length > 0 ? (
            <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
              {results.map((item) => (
                <li key={item.item_id} style={{ marginBottom: '1rem' }}>
                  <Stack spacing={0.5}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{item.title || '(untitled)'}</Typography>
                    {item.canonical_url || item.url ? (
                      <Typography
                        component="a"
                        href={item.canonical_url || item.url}
                        target="_blank"
                        rel="noreferrer"
                        variant="body2"
                        sx={{ color: 'primary.main', wordBreak: 'break-all' }}
                      >
                        {item.canonical_url || item.url}
                      </Typography>
                    ) : null}
                    <Typography variant="body2" color="text.secondary">
                      {item.summary || 'No description available.'}
                    </Typography>
                  </Stack>
                </li>
              ))}
            </ol>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  )
}
