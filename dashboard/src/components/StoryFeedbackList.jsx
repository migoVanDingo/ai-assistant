import { IconButton, Stack, Typography } from '@mui/material'
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined'
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt'
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined'
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import FavoriteButton from './FavoriteButton'

export default function StoryFeedbackList({
  items,
  sectionKey,
  emptyText = 'No links available.',
  onError,
  feedbackById,
  setFeedbackById,
  feedbackSaving,
  setFeedbackSaving,
}) {
  const [localFeedbackById, setLocalFeedbackById] = useState({})
  const [localFeedbackSaving, setLocalFeedbackSaving] = useState({})
  const activeFeedbackById = feedbackById || localFeedbackById
  const activeFeedbackSaving = feedbackSaving || localFeedbackSaving
  const writeFeedbackById = setFeedbackById || setLocalFeedbackById
  const writeFeedbackSaving = setFeedbackSaving || setLocalFeedbackSaving

  useEffect(() => {
    writeFeedbackById((current) => {
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
  }, [items, writeFeedbackById])

  const getFeedback = (item) => {
    const itemId = item?.item_id
    if (!itemId) return { vote: 0, score: 0 }
    return activeFeedbackById[itemId] || {
      vote: Number(item.feedback_vote || 0),
      score: Number(item.feedback_score || 0),
    }
  }

  const handleStoryVote = async (item, direction) => {
    const itemId = item?.item_id
    if (!itemId) return
    const current = getFeedback(item)
    const nextVote = current.vote === direction ? 0 : direction
    const optimistic = {
      vote: nextVote,
      score: Number(current.score || 0) + (nextVote - Number(current.vote || 0)),
      updated_at: new Date().toISOString(),
    }
    writeFeedbackById((state) => ({ ...state, [itemId]: optimistic }))
    writeFeedbackSaving((state) => ({ ...state, [itemId]: true }))
    try {
      const updated = await api.setStoryFeedback({ item_id: itemId, vote: nextVote, section: sectionKey })
      writeFeedbackById((state) => ({
        ...state,
        [itemId]: {
          vote: Number(updated.vote || 0),
          score: Number(updated.score || 0),
          updated_at: updated.updated_at || null,
        },
      }))
    } catch (err) {
      writeFeedbackById((state) => ({ ...state, [itemId]: current }))
      if (onError) onError(err.message || 'Failed to submit feedback.')
    } finally {
      writeFeedbackSaving((state) => ({ ...state, [itemId]: false }))
    }
  }

  if (!items?.length) {
    return <Typography color="text.secondary">{emptyText}</Typography>
  }

  return (
    <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
      {items.map((item) => {
        const feedback = getFeedback(item)
        const saving = Boolean(activeFeedbackSaving[item.item_id])
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
                  onClick={() => handleStoryVote(item, 1)}
                  disabled={saving}
                  aria-label="Thumbs up"
                >
                  {feedback.vote > 0 ? <ThumbUpAltIcon fontSize="small" /> : <ThumbUpAltOutlinedIcon fontSize="small" />}
                </IconButton>
                <IconButton
                  size="small"
                  color={feedback.vote < 0 ? 'error' : 'default'}
                  onClick={() => handleStoryVote(item, -1)}
                  disabled={saving}
                  aria-label="Thumbs down"
                >
                  {feedback.vote < 0 ? <ThumbDownAltIcon fontSize="small" /> : <ThumbDownAltOutlinedIcon fontSize="small" />}
                </IconButton>
                <FavoriteButton
                  title={item.title || item.url || item.canonical_url || '(untitled)'}
                  url={item.canonical_url || item.url}
                  itemId={item.item_id}
                />
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
}
