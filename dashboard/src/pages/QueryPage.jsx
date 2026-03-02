import { Grid2 as Grid, Stack } from '@mui/material'
import { useEffect, useState } from 'react'
import QueryPanel from '../components/QueryPanel'
import QueryResult from '../components/QueryResult'
import RecentQueries from '../components/RecentQueries'
import { api } from '../services/api'

export default function QueryPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [queries, setQueries] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [selectedQueryId, setSelectedQueryId] = useState('')

  const loadQueries = async (nextSelectedId = '') => {
    try {
      setHistoryLoading(true)
      const items = await api.listQueries({ days: 14, limit: 20 })
      setQueries(items)
      if (nextSelectedId) {
        setSelectedQueryId(nextSelectedId)
      } else if (!selectedQueryId && items[0]?.id) {
        setSelectedQueryId(items[0].id)
      }
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    loadQueries()
  }, [])

  const handleSubmit = async (query) => {
    try {
      setLoading(true)
      setError('')
      const payload = await api.query({ query })
      setResult(payload)
      setSelectedQueryId(payload.history_id || '')
      await loadQueries(payload.history_id || '')
    } catch (err) {
      setError(err.message || 'Query failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectQuery = async (queryId) => {
    try {
      setError('')
      setLoading(true)
      setSelectedQueryId(queryId)
      const payload = await api.getQuery(queryId)
      setResult(payload)
    } catch (err) {
      setError(err.message || 'Failed to load saved query.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack spacing={3}>
      <QueryPanel onSubmit={handleSubmit} loading={loading} error={error} />
      <Grid container spacing={3} alignItems="flex-start">
        <Grid size={{ xs: 12, lg: 4 }}>
          <RecentQueries
            items={queries}
            selectedId={selectedQueryId}
            loading={historyLoading}
            onSelect={handleSelectQuery}
          />
        </Grid>
        <Grid size={{ xs: 12, lg: 8 }}>
          <QueryResult result={result} />
        </Grid>
      </Grid>
    </Stack>
  )
}
