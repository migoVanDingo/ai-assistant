import { Alert, Box, CircularProgress, Grid2 as Grid, Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'
import BriefSidebar from '../components/BriefSidebar'
import BriefViewer from '../components/BriefViewer'
import MetricsCards from '../components/MetricsCards'
import { api } from '../services/api'

export default function BriefPage() {
  const [briefs, setBriefs] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const [briefList, metricPayload] = await Promise.all([api.listBriefs(), api.getMetrics()])
        setBriefs(briefList)
        setMetrics(metricPayload)
        const initialDate = briefList[0]?.date || ''
        setSelectedDate(initialDate)
        if (initialDate) {
          const brief = await api.getBrief(initialDate)
          setMarkdown(brief.markdown)
        }
      } catch (err) {
        setError(err.message || 'Failed to load dashboard data.')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleSelect = async (date) => {
    setSelectedDate(date)
    const brief = await api.getBrief(date)
    setMarkdown(brief.markdown)
  }

  if (loading) {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}><CircularProgress /></Box>
  }

  return (
    <Stack spacing={3}>
      <MetricsCards metrics={metrics} />
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Grid container spacing={3} alignItems="flex-start">
        <Grid size={{ xs: 12, md: 3 }}>
          <BriefSidebar briefs={briefs} selectedDate={selectedDate} onSelect={handleSelect} />
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          {selectedDate ? (
            <BriefViewer markdown={markdown} title={selectedDate} />
          ) : (
            <Typography color="text.secondary">No brief files found.</Typography>
          )}
        </Grid>
      </Grid>
    </Stack>
  )
}
