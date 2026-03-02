import { Grid2 as Grid, Stack, useMediaQuery } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import QueryPanel from '../components/QueryPanel'
import QueryResult from '../components/QueryResult'
import RecentQueries from '../components/RecentQueries'
import { api } from '../services/api'

export default function QueryPage({ queries, queriesLoading, refreshQueries }) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [searchParams, setSearchParams] = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const selectedQueryId = searchParams.get('queryId') || ''

  useEffect(() => {
    if (!selectedQueryId) {
      return
    }
    let cancelled = false
    async function loadSavedQuery() {
      try {
        setLoading(true)
        setError('')
        const payload = await api.getQuery(selectedQueryId)
        if (!cancelled) {
          setResult(payload)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load saved query.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    loadSavedQuery()
    return () => {
      cancelled = true
    }
  }, [selectedQueryId])

  const handleSubmit = async (query) => {
    try {
      setLoading(true)
      setError('')
      const payload = await api.query({ query })
      setResult(payload)
      if (payload.history_id) {
        setSearchParams({ queryId: payload.history_id })
      }
      await refreshQueries()
    } catch (err) {
      setError(err.message || 'Query failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectQuery = async (queryId) => {
    setSearchParams({ queryId })
  }

  return (
    <Stack spacing={3}>
      <QueryPanel onSubmit={handleSubmit} loading={loading} error={error} />
      <Grid container spacing={3} alignItems="flex-start">
        {!isMobile ? (
          <Grid size={{ md: 3 }}>
          <RecentQueries
            items={queries}
            selectedId={selectedQueryId}
            loading={queriesLoading}
            onSelect={handleSelectQuery}
          />
          </Grid>
        ) : null}
        <Grid size={{ xs: 12, md: 9 }}>
          <QueryResult result={result} />
        </Grid>
      </Grid>
    </Stack>
  )
}
