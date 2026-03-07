import { Box, IconButton, Typography } from '@mui/material'
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined'
import ThumbDownAltIcon from '@mui/icons-material/ThumbDownAlt'
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined'
import ThumbUpAltIcon from '@mui/icons-material/ThumbUpAlt'
import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../services/api'
import FavoriteButton from './FavoriteButton'

function textFromNode(node) {
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(textFromNode).join('')
  if (node && typeof node === 'object' && 'props' in node) return textFromNode(node.props?.children)
  return ''
}

export default function MarkdownContent({
  markdown,
  linkFeedbackMap = {},
  feedbackById,
  setFeedbackById,
  feedbackSaving,
  setFeedbackSaving,
}) {
  const emptyFeedback = useMemo(() => ({}), [])
  const activeFeedbackById = feedbackById || emptyFeedback
  const activeFeedbackSaving = feedbackSaving || emptyFeedback
  const writeFeedbackById = setFeedbackById || (() => {})
  const writeFeedbackSaving = setFeedbackSaving || (() => {})

  const getFeedback = (meta) => {
    const itemId = meta?.item_id
    if (!itemId) return { vote: 0, score: 0 }
    return activeFeedbackById[itemId] || { vote: Number(meta.vote || 0), score: Number(meta.score || 0) }
  }

  const handleVote = async (meta, direction) => {
    const itemId = meta?.item_id
    if (!itemId) return
    const current = getFeedback(meta)
    const nextVote = current.vote === direction ? 0 : direction
    const optimistic = {
      vote: nextVote,
      score: Number(current.score || 0) + (nextVote - Number(current.vote || 0)),
      updated_at: new Date().toISOString(),
    }
    writeFeedbackById((state) => ({ ...(state || {}), [itemId]: optimistic }))
    writeFeedbackSaving((state) => ({ ...(state || {}), [itemId]: true }))
    try {
      const updated = await api.setStoryFeedback({ item_id: itemId, vote: nextVote, section: meta.section || 'other_links' })
      writeFeedbackById((state) => ({
        ...(state || {}),
        [itemId]: {
          vote: Number(updated.vote || 0),
          score: Number(updated.score || 0),
          updated_at: updated.updated_at || null,
        },
      }))
    } catch {
      writeFeedbackById((state) => ({ ...(state || {}), [itemId]: current }))
    } finally {
      writeFeedbackSaving((state) => ({ ...(state || {}), [itemId]: false }))
    }
  }

  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => <Typography variant="h4" sx={{ mt: 1.5, mb: 2.5 }}>{children}</Typography>,
        h2: ({ children }) => <Typography variant="h5" sx={{ mt: 3, mb: 1.75 }}>{children}</Typography>,
        h3: ({ children }) => <Typography variant="h6" sx={{ mt: 2.5, mb: 1.25, color: 'primary.main' }}>{children}</Typography>,
        p: ({ children }) => <Typography variant="body1" sx={{ mb: 1.8, lineHeight: 1.85 }}>{children}</Typography>,
        li: ({ children }) => <li><Typography variant="body1" sx={{ mb: 1, lineHeight: 1.75 }}>{children}</Typography></li>,
        a: ({ href, children }) => {
          const url = String(href || '').trim()
          const meta = linkFeedbackMap[url]
          if (!meta?.item_id) {
            return <a href={href} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 700 }}>{children}</a>
          }
          const feedback = getFeedback(meta)
          const saving = Boolean(activeFeedbackSaving[meta.item_id])
          return (
            <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
              <a href={href} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 700 }}>{children}</a>
              <IconButton
                size="small"
                color={feedback.vote > 0 ? 'success' : 'default'}
                onClick={(event) => {
                  event.preventDefault()
                  handleVote(meta, 1)
                }}
                disabled={saving}
                aria-label="Thumbs up"
              >
                {feedback.vote > 0 ? <ThumbUpAltIcon fontSize="inherit" /> : <ThumbUpAltOutlinedIcon fontSize="inherit" />}
              </IconButton>
              <IconButton
                size="small"
                color={feedback.vote < 0 ? 'error' : 'default'}
                onClick={(event) => {
                  event.preventDefault()
                  handleVote(meta, -1)
                }}
                disabled={saving}
                aria-label="Thumbs down"
              >
                {feedback.vote < 0 ? <ThumbDownAltIcon fontSize="inherit" /> : <ThumbDownAltOutlinedIcon fontSize="inherit" />}
              </IconButton>
              <FavoriteButton
                title={textFromNode(children) || url}
                url={url}
                itemId={meta.item_id}
              />
              <Typography component="span" variant="caption" sx={{ color: 'text.secondary' }}>{Number(feedback.score || 0)}</Typography>
            </Box>
          )
        },
        em: ({ children }) => <Typography component="em" variant="body2" sx={{ color: 'text.secondary', display: 'block', mb: 1.5 }}>{children}</Typography>,
        code: ({ children }) => <code style={{ fontFamily: 'monospace' }}>{children}</code>,
      }}
    >
      {markdown || ''}
    </ReactMarkdown>
  )
}
