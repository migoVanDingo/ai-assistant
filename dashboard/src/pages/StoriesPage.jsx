import { LoadingButton } from '@mui/lab'
import {
  Alert,
  Box,
  CircularProgress,
  FormControl,
  IconButton,
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
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined'
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt'
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined'
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt'
import { useEffect, useMemo, useState } from 'react'
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
  const [loadingSections, setLoadingSections] = useState(true)
  const [error, setError] = useState('')
  const [sectionError, setSectionError] = useState('')
  const [sources, setSources] = useState([])
  const [clusters, setClusters] = useState([])
  const [tags, setTags] = useState([])
  const [watchHits, setWatchHits] = useState([])
  const [results, setResults] = useState([])
  const [sections, setSections] = useState({
    top_links: [],
    trending: [],
    suggested_links: [],
    other_links: [],
  })
  const [feedbackById, setFeedbackById] = useState({})
  const [feedbackSaving, setFeedbackSaving] = useState({})
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

  const mergeFeedbackState = (items) => {
    setFeedbackById((current) => {
      const next = { ...current }
      for (const item of items || []) {
        const itemId = item?.item_id
        if (!itemId || next[itemId]) continue
        next[itemId] = {
          vote: Number(item.feedback_vote || 0),
          score: Number(item.feedback_score || 0),
          updated_at: item.feedback_updated_at || null,
        }
      }
      return next
    })
  }

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
    async function loadSections() {
      try {
        setLoadingSections(true)
        setSectionError('')
        const payload = await api.listStorySections({ section_limit: 12 })
        if (cancelled) return
        const nextSections = {
          top_links: payload.top_links || [],
          trending: payload.trending || [],
          suggested_links: payload.suggested_links || [],
          other_links: payload.other_links || [],
        }
        setSections(nextSections)
        mergeFeedbackState([
          ...nextSections.top_links,
          ...nextSections.trending,
          ...nextSections.suggested_links,
          ...nextSections.other_links,
        ])
      } catch (err) {
        if (!cancelled) {
          setSectionError(err.message || 'Failed to load story sections.')
        }
      } finally {
        if (!cancelled) {
          setLoadingSections(false)
        }
      }
    }
    loadSections()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadStories() {
      try {
        setLoadingResults(true)
        setError('')
        const payload = await api.queryStories(appliedFilters)
        if (!cancelled) {
          const items = payload.items || []
          setResults(items)
          mergeFeedbackState(items)
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

  const getFeedback = (item) => {
    const itemId = item?.item_id
    if (!itemId) return { vote: 0, score: 0 }
    return feedbackById[itemId] || {
      vote: Number(item.feedback_vote || 0),
      score: Number(item.feedback_score || 0),
    }
  }

  const handleStoryVote = async (item, section, direction) => {
    const itemId = item?.item_id
    if (!itemId) return
    const current = getFeedback(item)
    const nextVote = current.vote === direction ? 0 : direction
    const optimistic = {
      vote: nextVote,
      score: Number(current.score || 0) + (nextVote - Number(current.vote || 0)),
      updated_at: new Date().toISOString(),
    }
    setFeedbackById((state) => ({ ...state, [itemId]: optimistic }))
    setFeedbackSaving((state) => ({ ...state, [itemId]: true }))
    try {
      const updated = await api.setStoryFeedback({ item_id: itemId, vote: nextVote, section })
      setFeedbackById((state) => ({
        ...state,
        [itemId]: {
          vote: Number(updated.vote || 0),
          score: Number(updated.score || 0),
          updated_at: updated.updated_at || null,
        },
      }))
    } catch (err) {
      setFeedbackById((state) => ({ ...state, [itemId]: current }))
      setSectionError(err.message || 'Failed to submit feedback.')
    } finally {
      setFeedbackSaving((state) => ({ ...state, [itemId]: false }))
    }
  }

  const renderStoryList = (items, sectionKey) => (
    <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
      {(items || []).map((item) => {
        const feedback = getFeedback(item)
        const saving = Boolean(feedbackSaving[item.item_id])
        return (
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
              <Stack direction="row" spacing={1} alignItems="center">
                <IconButton
                  size="small"
                  color={feedback.vote > 0 ? 'success' : 'default'}
                  onClick={() => handleStoryVote(item, sectionKey, 1)}
                  disabled={saving}
                  aria-label="Thumbs up"
                >
                  {feedback.vote > 0 ? <ThumbUpAltIcon fontSize="small" /> : <ThumbUpAltOutlinedIcon fontSize="small" />}
                </IconButton>
                <IconButton
                  size="small"
                  color={feedback.vote < 0 ? 'error' : 'default'}
                  onClick={() => handleStoryVote(item, sectionKey, -1)}
                  disabled={saving}
                  aria-label="Thumbs down"
                >
                  {feedback.vote < 0 ? <ThumbDownAltIcon fontSize="small" /> : <ThumbDownAltOutlinedIcon fontSize="small" />}
                </IconButton>
                <Typography variant="caption" color="text.secondary">
                  score {Number(feedback.score || 0)}
                </Typography>
              </Stack>
            </Stack>
          </li>
        )
      })}
    </ol>
  )

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

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Top links</Typography>
          {loadingSections ? (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={20} />
              <Typography color="text.secondary">Loading sections...</Typography>
            </Stack>
          ) : null}
          {!loadingSections && sections.top_links.length > 0 ? renderStoryList(sections.top_links, 'top_links') : null}
          {!loadingSections && sections.top_links.length === 0 ? (
            <Typography color="text.secondary">No top links available.</Typography>
          ) : null}
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Trending</Typography>
          {!loadingSections && sections.trending.length > 0 ? renderStoryList(sections.trending, 'trending') : null}
          {!loadingSections && sections.trending.length === 0 ? (
            <Typography color="text.secondary">No trending links available.</Typography>
          ) : null}
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Suggested links</Typography>
          <Typography variant="body2" color="text.secondary">
            Personalized from your article thumbs feedback. Suggestions consider links from the last 7 days.
          </Typography>
          {!loadingSections && sections.suggested_links.length > 0 ? renderStoryList(sections.suggested_links, 'suggested_links') : null}
          {!loadingSections && sections.suggested_links.length === 0 ? (
            <Typography color="text.secondary">No suggested links yet. Add thumbs up/down on stories to train this section.</Typography>
          ) : null}
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Other links</Typography>
          {!loadingSections && sections.other_links.length > 0 ? renderStoryList(sections.other_links, 'other_links') : null}
          {!loadingSections && sections.other_links.length === 0 ? (
            <Typography color="text.secondary">No additional links available.</Typography>
          ) : null}
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

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <div>
            <Typography variant="overline" color="text.secondary">Search focus</Typography>
            <Typography variant="h6">{heading}</Typography>
          </div>
          {sectionError ? <Alert severity="warning">{sectionError}</Alert> : null}
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
            <Box>{renderStoryList(results, 'other_links')}</Box>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  )
}
