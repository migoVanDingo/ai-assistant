import { Alert, CircularProgress, Grid2 as Grid, Paper, Stack, Typography, useMediaQuery } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { useEffect, useState } from 'react'
import BriefSidebar from '../components/BriefSidebar'
import BriefViewer from '../components/BriefViewer'
import MetricsCards from '../components/MetricsCards'
import StoryFeedbackList from '../components/StoryFeedbackList'
import { api } from '../services/api'

export default function BriefPage({ briefs, selectedDate, markdown, metrics, onSelectBrief }) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [sectionsLoading, setSectionsLoading] = useState(true)
  const [sectionsError, setSectionsError] = useState('')
  const [feedbackError, setFeedbackError] = useState('')
  const [feedbackById, setFeedbackById] = useState({})
  const [feedbackSaving, setFeedbackSaving] = useState({})
  const [sections, setSections] = useState({
    top_links: [],
    trending: [],
    suggested_links: [],
  })

  useEffect(() => {
    let cancelled = false
    async function loadSections() {
      try {
        setSectionsLoading(true)
        setSectionsError('')
        const payload = await api.listStorySections({ section_limit: 10 })
        if (cancelled) return
        setSections({
          top_links: payload.top_links || [],
          trending: payload.trending || [],
          suggested_links: payload.suggested_links || [],
        })
      } catch (err) {
        if (!cancelled) {
          setSectionsError(err.message || 'Failed to load brief story sections.')
        }
      } finally {
        if (!cancelled) {
          setSectionsLoading(false)
        }
      }
    }
    loadSections()
    return () => {
      cancelled = true
    }
  }, [selectedDate])

  return (
    <Stack spacing={3}>
      {!isMobile ? <MetricsCards metrics={metrics} /> : null}
      <Paper
        sx={{
          p: { xs: 2.5, md: 2.5 },
          pt: { xs: 3, md: 2.5 },
          minHeight: { xs: 132, md: 'auto' },
          borderRadius: 4,
        }}
      >
        <Typography variant="h5" sx={{ mb: 0.5 }}>Morning Brief Archive</Typography>
        <Typography color="text.secondary">
          Briefs are loaded directly from the markdown files in the briefs directory. Use the menu to switch views on mobile.
        </Typography>
      </Paper>
      <Grid container spacing={3} alignItems="flex-start">
        <Grid size={{ md: 3 }} sx={{ display: { xs: 'none', md: 'block' } }}>
          <BriefSidebar briefs={briefs} selectedDate={selectedDate} onSelect={onSelectBrief} />
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          <Stack spacing={3}>
            <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
              <Stack spacing={2}>
                <Typography variant="h6">Top links</Typography>
                {sectionsLoading ? (
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <CircularProgress size={20} />
                    <Typography color="text.secondary">Loading links...</Typography>
                  </Stack>
                ) : null}
                {sectionsError ? <Alert severity="error">{sectionsError}</Alert> : null}
                {feedbackError ? <Alert severity="warning">{feedbackError}</Alert> : null}
                {!sectionsLoading ? (
                  <StoryFeedbackList
                    items={sections.top_links}
                    sectionKey="top_links"
                    emptyText="No top links available."
                    onError={setFeedbackError}
                    feedbackById={feedbackById}
                    setFeedbackById={setFeedbackById}
                    feedbackSaving={feedbackSaving}
                    setFeedbackSaving={setFeedbackSaving}
                  />
                ) : null}
              </Stack>
            </Paper>

            <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
              <Stack spacing={2}>
                <Typography variant="h6">Trending</Typography>
                {!sectionsLoading ? (
                  <StoryFeedbackList
                    items={sections.trending}
                    sectionKey="trending"
                    emptyText="No trending links available."
                    onError={setFeedbackError}
                    feedbackById={feedbackById}
                    setFeedbackById={setFeedbackById}
                    feedbackSaving={feedbackSaving}
                    setFeedbackSaving={setFeedbackSaving}
                  />
                ) : null}
              </Stack>
            </Paper>

            <Paper sx={{ p: { xs: 2.5, md: 3 }, borderRadius: 4 }}>
              <Stack spacing={2}>
                <Typography variant="h6">Suggested links</Typography>
                <Typography variant="body2" color="text.secondary">
                  Personalized from your article thumbs feedback across sections.
                </Typography>
                {!sectionsLoading ? (
                  <StoryFeedbackList
                    items={sections.suggested_links}
                    sectionKey="suggested_links"
                    emptyText="No suggested links yet."
                    onError={setFeedbackError}
                    feedbackById={feedbackById}
                    setFeedbackById={setFeedbackById}
                    feedbackSaving={feedbackSaving}
                    setFeedbackSaving={setFeedbackSaving}
                  />
                ) : null}
              </Stack>
            </Paper>

          {selectedDate ? (
            <BriefViewer markdown={markdown} title={selectedDate} />
          ) : (
            <Typography color="text.secondary">No brief files found.</Typography>
          )}
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  )
}
