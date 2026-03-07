import { Alert, CircularProgress, Divider, Paper, Stack, Typography } from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'
import MarkdownContent from './MarkdownContent'

const HEADING_TO_SECTION = {
  'top links': 'top_links',
  trends: 'trending',
  opportunities: 'other_links',
  followups: 'other_links',
  'suggested links': 'suggested_links',
}

function buildSuggestedLinksSection(items) {
  if (!items?.length) {
    return '## Suggested Links\n\n_No suggested links yet._\n'
  }
  const lines = ['## Suggested Links', '']
  for (const [index, item] of items.entries()) {
    const title = (item?.title || '(untitled)').replace(/\]/g, '\\]')
    const link = item?.canonical_url || item?.url
    if (!link) continue
    lines.push(`${index + 1}. [${title}](${link})`)
  }
  lines.push('')
  return lines.join('\n')
}

function injectSuggestedLinks(markdown, suggestedItems) {
  const base = markdown || ''
  const suggestedBlock = buildSuggestedLinksSection(suggestedItems)
  if (/^##\s+Suggested Links\s*$/im.test(base)) {
    return base
  }
  const opportunitiesIndex = base.search(/^##\s+Opportunities\s*$/im)
  if (opportunitiesIndex >= 0) {
    return `${base.slice(0, opportunitiesIndex).trimEnd()}\n\n${suggestedBlock}\n${base.slice(opportunitiesIndex).trimStart()}`
  }
  return `${base.trimEnd()}\n\n${suggestedBlock}`.trim()
}

function extractSectionLinks(markdown) {
  const urlSection = {}
  let currentSection = ''
  for (const rawLine of (markdown || '').split('\n')) {
    const heading = rawLine.match(/^##\s+(.+)$/)
    if (heading) {
      const normalized = String(heading[1] || '').trim().toLowerCase()
      currentSection = HEADING_TO_SECTION[normalized] || ''
      continue
    }
    if (!currentSection) continue
    const matches = [...rawLine.matchAll(/\[[^\]]+\]\((https?:\/\/[^)\s]+)\)/g)]
    for (const match of matches) {
      const url = String(match[1] || '').trim()
      if (!url || urlSection[url]) continue
      urlSection[url] = currentSection
    }
  }
  return urlSection
}

export default function BriefViewer({ markdown, title }) {
  const [sectionsLoading, setSectionsLoading] = useState(true)
  const [sectionsError, setSectionsError] = useState('')
  const [feedbackById, setFeedbackById] = useState({})
  const [feedbackSaving, setFeedbackSaving] = useState({})
  const [suggestedItems, setSuggestedItems] = useState([])
  const [linkFeedbackMap, setLinkFeedbackMap] = useState({})

  useEffect(() => {
    let cancelled = false
    async function loadSuggested() {
      try {
        setSectionsLoading(true)
        setSectionsError('')
        const payload = await api.listStorySections({ section_limit: 10 })
        if (!cancelled) {
          setSuggestedItems(payload.suggested_links || [])
        }
      } catch (err) {
        if (!cancelled) {
          setSectionsError(err.message || 'Failed to load Suggested Links.')
          setSuggestedItems([])
        }
      } finally {
        if (!cancelled) {
          setSectionsLoading(false)
        }
      }
    }
    loadSuggested()
    return () => {
      cancelled = true
    }
  }, [title])

  const markdownWithSuggested = useMemo(() => injectSuggestedLinks(markdown || '', suggestedItems), [markdown, suggestedItems])

  useEffect(() => {
    let cancelled = false
    async function resolveLinks() {
      const urlToSection = extractSectionLinks(markdownWithSuggested)
      const urls = Object.keys(urlToSection)
      if (!urls.length) {
        if (!cancelled) {
          setLinkFeedbackMap({})
        }
        return
      }
      try {
        const payload = await api.resolveStoryLinks({ urls })
        if (cancelled) return
        const resolved = payload.items || {}
        const nextMap = {}
        const nextFeedback = {}
        for (const url of urls) {
          const item = resolved[url]
          if (!item?.item_id) continue
          nextMap[url] = {
            item_id: item.item_id,
            section: urlToSection[url] || 'other_links',
            vote: Number(item.feedback_vote || 0),
            score: Number(item.feedback_score || 0),
          }
          nextFeedback[item.item_id] = {
            vote: Number(item.feedback_vote || 0),
            score: Number(item.feedback_score || 0),
            updated_at: item.feedback_updated_at || null,
          }
        }
        setLinkFeedbackMap(nextMap)
        setFeedbackById((current) => ({ ...nextFeedback, ...current }))
      } catch {
        if (!cancelled) {
          setLinkFeedbackMap({})
        }
      }
    }
    resolveLinks()
    return () => {
      cancelled = true
    }
  }, [markdownWithSuggested])

  return (
    <Paper sx={{ p: { xs: 2.5, md: 4 }, borderRadius: 4 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 2 }}>
            Brief Reader
          </Typography>
          <Typography variant="h4">{title || 'Brief Content'}</Typography>
        </div>
        <Divider />
        {sectionsLoading ? (
          <Stack direction="row" spacing={1.25} alignItems="center">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">Refreshing Suggested Links...</Typography>
          </Stack>
        ) : null}
        {sectionsError ? <Alert severity="warning">{sectionsError}</Alert> : null}
      </Stack>
      <MarkdownContent
        markdown={markdownWithSuggested || '_No brief selected._'}
        linkFeedbackMap={linkFeedbackMap}
        feedbackById={feedbackById}
        setFeedbackById={setFeedbackById}
        feedbackSaving={feedbackSaving}
        setFeedbackSaving={setFeedbackSaving}
      />
    </Paper>
  )
}
