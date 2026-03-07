import { Alert, CircularProgress, IconButton, Paper, Stack, Typography } from '@mui/material'
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined'
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt'
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined'
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt'
import StarRoundedIcon from '@mui/icons-material/StarRounded'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../services/api'

export default function FavoritesPage() {
  const navigate = useNavigate()
  const { folderId } = useParams()
  const activeFolderId = folderId || 'favorites'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [folders, setFolders] = useState([])
  const [items, setItems] = useState([])
  const [folder, setFolder] = useState(null)
  const [feedbackById, setFeedbackById] = useState({})
  const [savingByItem, setSavingByItem] = useState({})
  const [removingByFavorite, setRemovingByFavorite] = useState({})

  const folderMap = useMemo(() => {
    const out = {}
    for (const value of folders || []) {
      out[value.folder_id] = value
    }
    return out
  }, [folders])

  useEffect(() => {
    let cancelled = false
    async function loadData() {
      try {
        setLoading(true)
        setError('')
        const [folderRows, listPayload] = await Promise.all([
          api.listFavoriteFolders(),
          api.listFavoriteItems({ folder_id: activeFolderId }),
        ])
        if (cancelled) return
        setFolders(folderRows || [])
        setFolder(listPayload?.folder || null)
        let nextItems = listPayload?.items || []
        const urlsToResolve = nextItems.filter((item) => !item.item_id).map((item) => item.url).filter(Boolean)
        if (urlsToResolve.length) {
          const resolved = await api.resolveStoryLinks({ urls: urlsToResolve })
          const byUrl = resolved?.items || {}
          nextItems = nextItems.map((item) => {
            if (item.item_id) return item
            const resolvedItem = byUrl[item.url]
            if (!resolvedItem?.item_id) return item
            return {
              ...item,
              item_id: resolvedItem.item_id,
              feedback_vote: Number(resolvedItem.feedback_vote || 0),
              feedback_score: Number(resolvedItem.feedback_score || 0),
              feedback_updated_at: resolvedItem.feedback_updated_at || null,
            }
          })
        }
        setItems(nextItems)
        setFeedbackById((current) => {
          const next = { ...current }
          for (const item of nextItems) {
            if (!item.item_id || next[item.item_id]) continue
            next[item.item_id] = {
              vote: Number(item.feedback_vote || 0),
              score: Number(item.feedback_score || 0),
              updated_at: item.feedback_updated_at || null,
            }
          }
          return next
        })
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load favorites.')
          setFolders([])
          setItems([])
          setFolder(null)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    loadData()
    return () => {
      cancelled = true
    }
  }, [activeFolderId])

  useEffect(() => {
    if (!loading && folderId && !folderMap[folderId]) {
      navigate('/favorites', { replace: true })
    }
  }, [folderId, folderMap, loading, navigate])

  const getFeedback = (item) => {
    if (!item?.item_id) return { vote: 0, score: 0 }
    return feedbackById[item.item_id] || {
      vote: Number(item.feedback_vote || 0),
      score: Number(item.feedback_score || 0),
    }
  }

  const submitVote = async (item, direction) => {
    if (!item?.item_id) return
    const current = getFeedback(item)
    const nextVote = current.vote === direction ? 0 : direction
    const optimistic = {
      vote: nextVote,
      score: Number(current.score || 0) + (nextVote - Number(current.vote || 0)),
      updated_at: new Date().toISOString(),
    }
    setFeedbackById((state) => ({ ...state, [item.item_id]: optimistic }))
    setSavingByItem((state) => ({ ...state, [item.item_id]: true }))
    try {
      const updated = await api.setStoryFeedback({ item_id: item.item_id, vote: nextVote, section: 'other_links' })
      setFeedbackById((state) => ({
        ...state,
        [item.item_id]: {
          vote: Number(updated.vote || 0),
          score: Number(updated.score || 0),
          updated_at: updated.updated_at || null,
        },
      }))
    } catch (err) {
      setFeedbackById((state) => ({ ...state, [item.item_id]: current }))
      setError(err.message || 'Failed to submit feedback.')
    } finally {
      setSavingByItem((state) => ({ ...state, [item.item_id]: false }))
    }
  }

  const removeFavorite = async (item) => {
    if (!item?.favorite_id) return
    setRemovingByFavorite((state) => ({ ...state, [item.favorite_id]: true }))
    try {
      await api.removeFavoriteItem({ favorite_id: item.favorite_id })
      setItems((current) => current.filter((value) => value.favorite_id !== item.favorite_id))
      setFolders((current) => current.map((row) => (
        row.folder_id === activeFolderId ? { ...row, count: Math.max(0, Number(row.count || 0) - 1) } : row
      )))
    } catch (err) {
      setError(err.message || 'Failed to remove favorite.')
    } finally {
      setRemovingByFavorite((state) => ({ ...state, [item.favorite_id]: false }))
    }
  }

  return (
    <Stack spacing={3}>
      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={0.75}>
          <Typography variant="h5">Favorites</Typography>
          <Typography color="text.secondary">
            Open a folder to view saved links. Star is active in this view and removes the link from the folder.
          </Typography>
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 4 }}>
        <Stack spacing={1.25} direction="row" sx={{ overflowX: 'auto' }}>
          {(folders || []).map((entry) => {
            const to = entry.folder_id === 'favorites' ? '/favorites' : `/favorites/${entry.folder_id}`
            const active = activeFolderId === entry.folder_id
            return (
              <Typography
                key={entry.folder_id}
                component={Link}
                to={to}
                sx={{
                  textDecoration: 'none',
                  px: 1.5,
                  py: 0.9,
                  borderRadius: 999,
                  whiteSpace: 'nowrap',
                  border: 1,
                  borderColor: active ? 'primary.main' : 'divider',
                  color: active ? 'primary.main' : 'text.secondary',
                }}
              >
                {entry.name} ({entry.count || 0})
              </Typography>
            )
          })}
        </Stack>
      </Paper>

      <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{folder?.name || 'favorites'}</Typography>
          {error ? <Alert severity="warning">{error}</Alert> : null}
          {loading ? (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={20} />
              <Typography color="text.secondary">Loading favorites...</Typography>
            </Stack>
          ) : null}
          {!loading && items.length === 0 ? (
            <Typography color="text.secondary">No links in this folder.</Typography>
          ) : null}
          {!loading && items.length > 0 ? (
            <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
              {items.map((item) => {
                const feedback = getFeedback(item)
                const voteSaving = Boolean(item.item_id && savingByItem[item.item_id])
                const removing = Boolean(removingByFavorite[item.favorite_id])
                return (
                  <li key={item.favorite_id} style={{ marginBottom: '1rem' }}>
                    <Stack spacing={0.5}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{item.title || '(untitled)'}</Typography>
                      <Typography
                        component="a"
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        variant="body2"
                        sx={{ color: 'primary.main', wordBreak: 'break-all' }}
                      >
                        {item.url}
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <IconButton
                          size="small"
                          color={feedback.vote > 0 ? 'success' : 'default'}
                          onClick={() => submitVote(item, 1)}
                          disabled={!item.item_id || voteSaving || removing}
                          aria-label="Thumbs up"
                        >
                          {feedback.vote > 0 ? <ThumbUpAltIcon fontSize="small" /> : <ThumbUpAltOutlinedIcon fontSize="small" />}
                        </IconButton>
                        <IconButton
                          size="small"
                          color={feedback.vote < 0 ? 'error' : 'default'}
                          onClick={() => submitVote(item, -1)}
                          disabled={!item.item_id || voteSaving || removing}
                          aria-label="Thumbs down"
                        >
                          {feedback.vote < 0 ? <ThumbDownAltIcon fontSize="small" /> : <ThumbDownAltOutlinedIcon fontSize="small" />}
                        </IconButton>
                        <IconButton
                          size="small"
                          color="warning"
                          onClick={() => removeFavorite(item)}
                          disabled={removing}
                          aria-label="Remove favorite"
                        >
                          <StarRoundedIcon fontSize="small" />
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
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  )
}
