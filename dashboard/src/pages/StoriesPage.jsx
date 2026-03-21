import { LoadingButton } from '@mui/lab'
import {
  Alert,
  Box,
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
import StoryFeedbackList from '../components/StoryFeedbackList'
import { api } from '../services/api'

const LIMIT_OPTIONS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

function dedupeBy(items, keyFn) {
  const seen = new Set()
  return items.filter((item) => {
    const key = keyFn(item)
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

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
  const [feedbackError, setFeedbackError] = useState('')
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
  const [appliedFilters, setAppliedFilters] = useState({
    source_name: '',
    from_date: '',
    to_date: '',
    limit: 20,
    cluster_id: '',
    tags: [],
    watch_hits: [],
    order: 'desc',
  })

  const normalizeMultiValue = (value) => (Array.isArray(value) ? value : String(value).split(',').filter(Boolean))

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
        setSources(dedupeBy(sourceList, (item) => String(item).toLowerCase()))
        setClusters(dedupeBy(clusterList, (item) => ((item.label || item.id || '').trim().toLowerCase())))
        setTags(dedupeBy(tagList, (item) => String(item.tag || '').trim().toLowerCase()))
        setWatchHits(dedupeBy(watchHitList, (item) => String(item.watch_hit || '').trim().toLowerCase()))
      } catch (err) {
        setError(err.message || 'Failed to load story filters.')
      } finally {
        setLoadingOptions(false)
      }
    }
    loadOptions()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadStories() {
      try {
        setLoadingResults(true)
        setError('')
        const payload = await api.queryStories(appliedFilters)
        if (!cancelled) {
          setResults(payload.items || [])
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load stories.')
          setResults([])
        }
      } finally {
        if (!cancelled) {
          setLoadingResults(false)
        }
      }
    }
    loadStories()
    return () => {
      cancelled = true
    }
  }, [appliedFilters])

  const heading = useMemo(() => buildHeading(appliedFilters, clusters), [appliedFilters, clusters])

  return (
    <Stack spacing={3} sx={{ width: '100%', overflowX: 'hidden' }}>
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
          <Box
            sx={{
              overflowX: 'auto',
              WebkitOverflowScrolling: 'touch',
              mx: -2,
              px: 2,
              pb: 1,
              maskImage: {
                xs: 'linear-gradient(to right, transparent 0, black 8px, black calc(100% - 24px), transparent 100%)',
                md: 'linear-gradient(to right, transparent 0, black 8px, black calc(100% - 32px), transparent 100%)',
              },
              '&::-webkit-scrollbar': { height: 6 },
              '&::-webkit-scrollbar-thumb': {
                borderRadius: 3,
                bgcolor: 'action.hover',
              },
            }}
          >
            <Stack direction="row" spacing={1} sx={{ width: 'max-content', py: 0.5 }}>
              {sources.map((source) => (
                <ToggleButton
                  key={source}
                  value={source}
                  selected={filters.source_name === source}
                  onChange={() => setFilters((current) => ({ ...current, source_name: current.source_name === source ? '' : source }))}
                  size="small"
                  sx={{
                    whiteSpace: 'nowrap',
                    borderRadius: 999,
                    flexShrink: 0,
                  }}
                >
                  {source}
                </ToggleButton>
              ))}
            </Stack>
          </Box>
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
            <LoadingButton
              variant="contained"
              loading={loadingResults}
              onClick={() => setAppliedFilters({ ...filters, tags: [...filters.tags], watch_hits: [...filters.watch_hits] })}
            >
              Apply filters
            </LoadingButton>
          </Stack>
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4, overflow: 'hidden' }}>
        <Stack spacing={2}>
          <div>
            <Typography variant="overline" color="text.secondary">Search focus</Typography>
            <Typography variant="h6">{heading}</Typography>
          </div>
          {feedbackError ? <Alert severity="warning">{feedbackError}</Alert> : null}
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
            <Box>
              <StoryFeedbackList items={results} sectionKey="other_links" onError={setFeedbackError} />
            </Box>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  )
}
