import { Alert, Box, CircularProgress, Container } from '@mui/material'
import { useEffect, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import HeaderBar from './components/HeaderBar'
import BriefPage from './pages/BriefPage'
import QueryPage from './pages/QueryPage'
import StoriesPage from './pages/StoriesPage'
import { api } from './services/api'

export default function App() {
  const [briefs, setBriefs] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [archiveLoading, setArchiveLoading] = useState(true)
  const [archiveError, setArchiveError] = useState('')

  useEffect(() => {
    console.info('[dashboard build]', __APP_BUILD_SHA__, __APP_BUILD_TIME__)
    window.__BRIEFBOT_BUILD__ = { sha: __APP_BUILD_SHA__, builtAt: __APP_BUILD_TIME__ }
  }, [])

  useEffect(() => {
    async function loadArchive() {
      try {
        setArchiveLoading(true)
        setArchiveError('')
        const [briefList, metricPayload] = await Promise.all([api.listBriefs(), api.getMetrics()])
        setBriefs(briefList)
        setMetrics(metricPayload)
        const initialDate = briefList[0]?.date || ''
        setSelectedDate(initialDate)
        if (initialDate) {
          const brief = await api.getBrief(initialDate)
          setMarkdown(brief.markdown)
        } else {
          setMarkdown('')
        }
      } catch (err) {
        setArchiveError(err.message || 'Failed to load dashboard data.')
      } finally {
        setArchiveLoading(false)
      }
    }
    loadArchive()
  }, [])

  const handleSelectBrief = async (date) => {
    try {
      setArchiveError('')
      setSelectedDate(date)
      const brief = await api.getBrief(date)
      setMarkdown(brief.markdown)
    } catch (err) {
      setArchiveError(err.message || 'Failed to load brief.')
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: (theme) =>
          theme.palette.mode === 'dark'
            ? 'radial-gradient(circle at top right, rgba(90,176,255,0.18), transparent 28%), linear-gradient(180deg, #0b1220 0%, #0f1725 38%, #0b1220 100%)'
            : 'radial-gradient(circle at top right, rgba(23,105,170,0.12), transparent 25%), linear-gradient(180deg, #f4f7fb 0%, #eef4fa 36%, #f6f9fc 100%)',
      }}
    >
      <HeaderBar
        briefs={briefs}
        selectedDate={selectedDate}
        onSelectBrief={handleSelectBrief}
      />
      <Container maxWidth="xl" sx={{ py: { xs: 2.5, md: 4 } }}>
        {archiveError ? <Alert severity="error" sx={{ mb: 2.5 }}>{archiveError}</Alert> : null}
        <Routes>
          <Route
            path="/"
            element={
              archiveLoading ? (
                <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
                  <CircularProgress />
                </Box>
              ) : (
                <BriefPage
                  briefs={briefs}
                  selectedDate={selectedDate}
                  markdown={markdown}
                  metrics={metrics}
                  onSelectBrief={handleSelectBrief}
                />
              )
            }
          />
          <Route path="/ask" element={<QueryPage />} />
          <Route path="/stories" element={<StoriesPage />} />
        </Routes>
        <Box component="footer" sx={{ mt: 4, pb: 2, color: 'text.secondary', fontSize: 12 }}>
          Build {__APP_BUILD_SHA__} · {new Date(__APP_BUILD_TIME__).toLocaleString()}
        </Box>
      </Container>
    </Box>
  )
}
